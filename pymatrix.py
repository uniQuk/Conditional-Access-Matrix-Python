#!/usr/bin/env python

import os
import argparse
import random
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import csv

# Import required modules for Microsoft Graph API
from msal import ConfidentialClientApplication
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Global variables for Microsoft Graph API authentication
TENANT_ID = os.getenv('TENANTID')
CLIENT_ID = os.getenv('CLIENTID')
CLIENT_SECRET = os.getenv('CLIENTSECRET')

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Analyze Conditional Access policies")
    parser.add_argument('--include-report-only', action='store_true', help='Include policies in report-only mode')
    parser.add_argument('-n', '--number', type=int, help='Limit the number of users to process')
    parser.add_argument('-g', '--groups', nargs='+', help='Filter users by group names or object IDs')
    parser.add_argument('-t', '--type', choices=['member', 'guest'], help='Filter by user type (member or guest)')
    parser.add_argument('-s', '--sample', type=float, help='Process a random sample of users (e.g., 0.1 for 10%)')
    parser.add_argument('-p', '--parallel', type=int, default=1, help='Number of parallel processes to use')
    parser.add_argument('--timeout', type=int, default=10, help='Timeout for requests to Microsoft Graph API (in seconds)')
    parser.add_argument('--no-pause', action='store_true', help='Do not pause at the end of the script')
    return parser.parse_args()

def get_token():
    """Acquire a token for Microsoft Graph API."""
    app = ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" in result:
        return result["access_token"]
    else:
        print(f"Error acquiring token: {result.get('error')}")
        exit(1)

def call_microsoft_graph(endpoint, token, timeout=10):
    """Make a call to Microsoft Graph."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    response = requests.get(f"https://graph.microsoft.com/v1.0{endpoint}", headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()

def get_all_with_next_link(token, endpoint, timeout):
    """Fetch all results from Microsoft Graph API, handling pagination."""
    results = []
    while endpoint:
        data = call_microsoft_graph(endpoint, token, timeout)
        results.extend(data.get('value', []))
        endpoint = data.get('@odata.nextLink', '').replace('https://graph.microsoft.com/v1.0', '')
    return results

def get_group_members(group, token, timeout):
    """Fetch members of a specific group."""
    members = []
    endpoint = f"/groups/{group}/members"
    while endpoint:
        data = call_microsoft_graph(endpoint, token, timeout)
        members.extend(data.get('value', []))
        endpoint = data.get('@odata.nextLink', '').replace('https://graph.microsoft.com/v1.0', '')
    return [member['id'] for member in members]

def calculate_included(policy, user, group_list):
    """Determine if a user is included in a Conditional Access policy."""
    if user['id'] in policy['conditions']['users'].get('excludeUsers', []):
        return False
    
    excluded_groups = policy['conditions']['users'].get('excludeGroups', [])
    if any(group in excluded_groups for group in group_list):
        return False
    
    if 'All' in policy['conditions']['users'].get('includeUsers', []):
        return True
    
    if user['id'] in policy['conditions']['users'].get('includeUsers', []):
        return True
    
    included_groups = policy['conditions']['users'].get('includeGroups', [])
    return any(group in included_groups for group in group_list)

def process_user(user, ca_policies, token, timeout):
    """Process a single user against all Conditional Access policies."""
    user_result = {
        'user': user.get('displayName', '').replace(',', '').replace(';', ''),
        'upn': user.get('userPrincipalName', '').replace(',', ''),
        'job': (user.get('jobTitle') or '').replace(',', '').replace(';', ''),
        'external': '#EXT#' in user.get('userPrincipalName', ''),
        'enabled': user.get('accountEnabled', False)
    }

    # Fetch the groups the user is a member of
    groups = call_microsoft_graph(f"/users/{user['id']}/memberOf?$select=id", token, timeout)
    group_list = [group['id'] for group in groups.get('value', [])]

    # Check each policy to see if the user is included
    for policy in ca_policies:
        user_result[policy['displayName']] = calculate_included(policy, user, group_list)

    return user_result

def export_to_csv(data, filename):
    """Export data to a CSV file."""
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    print(f"CSV file saved: {filename}")

def export_to_json(data, filename):
    """Export data to a JSON file."""
    with open(filename, 'w', encoding='utf-8') as jsonfile:
        json.dump(data, jsonfile, indent=2)
    print(f"JSON file saved: {filename}")

def main():
    """Main function to orchestrate the Conditional Access analysis."""
    args = parse_arguments()
    token = get_token()

    print(f"Connected to tenant '{TENANT_ID}'")

    # Fetch Conditional Access policies
    print("Fetching Conditional Access policies...")
    if args.include_report_only:
        ca_policies = get_all_with_next_link(token, "/policies/conditionalAccessPolicies?$filter=state eq 'enabled' or state eq 'enabledForReportingButNotEnforced'", args.timeout)
    else:
        ca_policies = get_all_with_next_link(token, "/policies/conditionalAccessPolicies?$filter=state eq 'enabled'", args.timeout)
    print(f"{len(ca_policies)} Conditional Access policies found")

    # Fetch users
    print("Fetching users...")
    users = get_all_with_next_link(token, "/users?$select=id,userPrincipalName,displayName,jobTitle,accountEnabled,userType", args.timeout)
    print(f"{len(users)} users found")

    # Filter users based on command-line arguments
    if args.groups:
        group_members = set()
        for group in args.groups:
            members = get_group_members(group, token, args.timeout)
            group_members.update(members)
        users = [user for user in users if user['id'] in group_members]

    if args.type:
        users = [user for user in users if user.get('userType', '').lower() == args.type]

    if args.sample:
        sample_size = int(len(users) * args.sample)
        users = random.sample(users, sample_size)

    if args.number:
        users = users[:args.number]

    print(f"{len(users)} users after filtering")

    result_obj = []
    total_users = len(users)

    # Process users (in parallel if specified)
    if args.parallel > 1:
        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            futures = [executor.submit(process_user, user, ca_policies, token, args.timeout) for user in users]
            for i, future in enumerate(as_completed(futures)):
                result_obj.append(future.result())
                print(f"\rProgress: {((i+1)/total_users)*100:.2f}% ({total_users - (i+1)} user(s) remaining)", end='', flush=True)
    else:
        for i, user in enumerate(users):
            result_obj.append(process_user(user, ca_policies, token, args.timeout))
            print(f"\rProgress: {((i+1)/total_users)*100:.2f}% ({total_users - (i+1)} user(s) remaining)", end='', flush=True)

    print("\nMatrix generation complete.")

    # Export results
    now = datetime.now()
    date_time = now.strftime("%Y-%m-%d-%H%M")
    csv_filename = f"{date_time}-CA-Impact-Matrix.csv"
    json_filename = f"{date_time}-CA-Impact-Matrix.json"
    
    export_to_csv(result_obj, csv_filename)
    export_to_json(result_obj, json_filename)

    print(f"\nScript executed in: {os.getcwd()}")
    if not args.no_pause:
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()