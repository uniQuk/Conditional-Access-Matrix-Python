# Conditional-Access-Matrix-Python

This is a rewrite in Python of: https://github.com/jasperbaes/Conditional-Access-Matrix

Usage:
pymatrix.py [-h] [--include-report-only] [-n NUMBER] [-g GROUPS [GROUPS ...]] [-t {member,guest}] [-s SAMPLE] [-p PARALLEL] [--timeout TIMEOUT] [--no-pause]

Examples:

### Output for specific number of users (first 10, 100, 1000) etc
- python pymatrix.py --include-report-only -n 10 --timeout 5

### Random sample in percent of total 0.2 = 20%
- python pymatrix.py --include-report-only -s 0.2

### Assess a specific group
- python pymatrix.py --include-report-only -g "bcfaa207-14fb-4610-ab02-8e32e6273b2a,"

#### Default timeout is 10 seconds and can be modified with --timeout <seconds> 

=============================================================================

## Limitations
- Subgroups might not be fully evaluated
- Conditional Access policies scoped on users with Entra roles might not be evaluated

## License

Please be aware that the Conditional Access Impact Matrix code is intended solely for individual administrators' personal use. It is not licensed for use by organizations seeking financial gain. This restriction is in place to ensure the responsible and fair use of the tool. Admins are encouraged to leverage this code to enhance their own understanding and management within their respective environments, but any commercial or organizational profit-driven usage is strictly prohibited.
