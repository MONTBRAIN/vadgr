#!/usr/bin/env sh
set -eu

label=${1:?usage: snapshot-unix.sh LABEL OUTPUT}
output=${2:?usage: snapshot-unix.sh LABEL OUTPUT}

hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}'
    else
        shasum -a 256 | awk '{print $1}'
    fi
}

hash_file() {
    path=$1
    if [ -f "$path" ]; then
        if command -v sha256sum >/dev/null 2>&1; then
            sha256sum "$path" | awk '{print $1}'
        else
            shasum -a 256 "$path" | awk '{print $1}'
        fi
    else
        printf 'absent\n'
    fi
}

hash_tree() {
    path=$1
    if [ ! -d "$path" ]; then
        printf 'absent\n'
        return
    fi
    find "$path" -type f -print 2>/dev/null | LC_ALL=C sort | hash_stream
}

{
    printf 'label=%s\n' "$label"
    printf 'bashrc=%s\n' "$(hash_file "$HOME/.bashrc")"
    printf 'zshrc=%s\n' "$(hash_file "$HOME/.zshrc")"
    printf 'profile=%s\n' "$(hash_file "$HOME/.profile")"
    printf 'python_user=%s\n' "$(hash_tree "$HOME/.local/lib")"
    printf 'pip_cache=%s\n' "$(hash_tree "$HOME/.cache/pip")"
    printf 'uv_cache=%s\n' "$(hash_tree "$HOME/.cache/uv")"
    printf 'python_env=%s\n' "$({
        for name in VIRTUAL_ENV PYTHONHOME PYTHONPATH PIP_CONFIG_FILE UV_CONFIG_FILE; do
            printf '%s=' "$name"
            printenv "$name" 2>/dev/null || true
            printf '\n'
        done
    } | hash_stream)"
    printf 'network=%s\n' "$({
        cat /etc/resolv.conf 2>/dev/null || true
        if command -v ip >/dev/null 2>&1; then ip route show 2>/dev/null || true; fi
        # Configuration, not neighbour state. `netstat -rn` mixes the routing
        # table with the ARP and NDP caches, and on macOS there is no `ip`, so
        # those caches were the whole network hash. They move on their own: an
        # Expire column counts down every second, entry flags age from `UHLWIi`
        # to `UHLWI`, and a VPN peer route appears and vanishes as the peer
        # comes and goes. Measured on an idle machine with vadgr not running at
        # all, the table changed twice in ninety seconds, so the non-mutation
        # comparison could never pass on a host with a tailnet or a busy LAN.
        #
        # Rows reached through a link-layer address or an interface scope are
        # that cache. What is left is the configuration a change would show up
        # in: destination, gateway and interface, defaults included.
        if command -v netstat >/dev/null 2>&1; then
            netstat -rn 2>/dev/null \
                | awk '$2 !~ /:/ && $2 !~ /^link#/ { print $1, $2, $4 }' || true
        fi
    } | hash_stream)"
} > "$output"
