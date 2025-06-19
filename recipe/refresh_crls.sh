#!/usr/bin/env bash
IFS=$'\n\t'

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

for crl_url_file in "${SCRIPT_DIR}"/*.crl_url
do
    pem=${crl_url_file//crl_url/pem}
    echo "${pem}";
    for subject_hash in $(openssl x509 -in "${pem}" -noout -subject_hash -subject_hash_old);
    do
        echo "${subject_hash}";
        echo "${crl_url_file}";
        curl -L --max-time 10 "$(cat "${crl_url_file}")" | openssl crl > "${SCRIPT_DIR}/${subject_hash}.r0" ;
    done
done