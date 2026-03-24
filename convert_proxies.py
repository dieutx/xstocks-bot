"""Convert proxies from host:port:user:pass format to http://user:pass@host:port"""
import sys
import re

pattern = re.compile(r'^([\w.]+):(\d+):([^:]+):(.+)$')

input_file = sys.argv[1] if len(sys.argv) > 1 else "data/raw_proxies.txt"
output_file = sys.argv[2] if len(sys.argv) > 2 else "data/new_proxies.txt"

count = 0
with open(input_file) as f, open(output_file, 'w') as out:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = pattern.match(line)
        if m:
            host, port, user, pwd = m.groups()
            out.write(f'http://{user}:{pwd}@{host}:{port}\n')
            count += 1

print(f"Converted {count} proxies → {output_file}")
