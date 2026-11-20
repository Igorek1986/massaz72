#!/bin/sh
set -eu

origin=${1:-https://massaz72.ru}

check_asset() {
    asset=$1
    expected_type=$2
    response=$(curl --silent --show-error --max-time 10 --output /dev/null \
        --write-out '%{http_code} %{size_download} %{content_type}' "${origin%/}$asset")
    IFS=' ' read -r status size content_type <<EOF
$response
EOF
    content_type=${content_type%%;*}
    if [ "$status" != 200 ] || [ "$size" -le 0 ] || [ "$content_type" != "$expected_type" ]; then
        printf '%s: HTTP %s, %s bytes, Content-Type %s\n' "$asset" "$status" "$size" "$content_type" >&2
        return 1
    fi
    printf '%s: HTTP %s, %s\n' "$asset" "$status" "$content_type"
}

check_asset /static/css/main.css text/css
check_asset /static/css/vendor.css text/css
check_asset /static/robots.txt text/plain

# The nginx vhost preserves the public robots URL.
if [ "${origin%/}" = https://massaz72.ru ]; then
    check_asset /robots.txt text/plain
fi
