#!/usr/bin/env python3
import gzip
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

base_url = 'https://repository.egi.eu/sw/production/cas/1/current/'
metapackage_name = 'ca-policy-lcg'

# Parse the repo manifest
response = requests.get(base_url+'repodata/repomd.xml')
assert response.ok
root = ET.fromstring(response.content)
for element in list(root):
    if element.attrib.get('type') == 'primary':
        location = element.find('./{http://linux.duke.edu/metadata/repo}location')
        primary_url = base_url+location.attrib['href']

    if element.attrib.get('type') == 'filelists':
        location = element.find('./{http://linux.duke.edu/metadata/repo}location')
        filelists_url = base_url+location.attrib['href']

assert filelists_url and primary_url

# Parse the RPM requirements
response = requests.get(primary_url)
assert response.ok
root = ET.fromstring(gzip.decompress(response.content))
dependency_map = {}
for package in root.findall('{http://linux.duke.edu/metadata/common}package'):
    name = package.find('{http://linux.duke.edu/metadata/common}name').text
    print(name)
    dependencies = package.find('{http://linux.duke.edu/metadata/common}format')
    dependencies = dependencies.find('{http://linux.duke.edu/metadata/rpm}requires')
    if dependencies:
        dependency_map[name] = {d.attrib['name'] for d in dependencies}

to_install = {metapackage_name}
checked = to_install.copy()
while checked:
    dep_name = checked.pop()
    if dep_name in dependency_map:
        to_install = to_install.union(dependency_map[dep_name])
        checked = checked.union(dependency_map[dep_name])

response = requests.get(filelists_url)
assert response.ok

# Compute the tarball hashes
urls = {}
past_version = None
root = ET.fromstring(gzip.decompress(response.content))
for package in root.findall('{http://linux.duke.edu/metadata/filelists}package'):
    name = package.attrib.get('name')
    if package.attrib.get('arch') != 'src':
        # print('Skipping', name)
        continue
    if name not in to_install:
        print('Skipping unrequired tarball', name)
        continue

    version = package.find('{http://linux.duke.edu/metadata/filelists}version')
    version = version.attrib['ver']
    assert past_version is None or version == past_version
    past_version = version

    files = [f.text for f in package.findall('{http://linux.duke.edu/metadata/filelists}file')]
    gz_files = [fn for fn in files if fn.endswith('.tar.gz')]
    assert len(gz_files) == 1, files

    url = base_url+'tgz/'+gz_files[0]
    response = requests.get(url)
    assert response.ok

    file_hash = hashlib.sha256()
    file_hash.update(response.content)
    print('Got hash', file_hash.hexdigest(), 'for', package.attrib.get('name'))
    urls[url.replace(version, '{{ version }}')] = file_hash.hexdigest()

    to_install.remove(name)

# Print the results
recipe_path = Path(__file__).parent / 'meta.yaml'
raw_yaml = recipe_path.read_text()
raw_yaml, n = re.subn(r'version = "\d+\.\d+"', f'version = "{version}"', raw_yaml)
if n != 1:
    raise ValueError('Could not find the version in the recipe')

start, end = re.search(r"source:\n(\s{2,}[^\n]+\n)+", raw_yaml).span()
if not raw_yaml[end:].startswith('\nbuild:\n'):
    raise ValueError('Could not find the build section in the recipe')
new_sources = [raw_yaml[:start], "source:"]
for url, file_hash in urls.items():
    new_sources += [
        f'  - url: {url}',
        f'    sha256: {file_hash}',
        f'    folder: {metapackage_name}'
    ]
new_sources += [raw_yaml[end:]]
new_sources = '\n'.join(new_sources)
recipe_path.write_text(new_sources)
print('Updated the recipe with the new sources')
