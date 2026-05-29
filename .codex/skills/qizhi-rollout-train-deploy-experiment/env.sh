#!/usr/bin/env bash

# Prepare caller-provided credentials for the qz/myqz CLI.
#
# Usage:
#   export QZ_API_USERNAME='your-api-username'
#   export QZ_API_PASSWORD='your-api-password'
#   export QZ_COOKIE_USERNAME='your-cookie-username'
#   export QZ_COOKIE_PASSWORD='your-cookie-password'
#   source .codex/skills/qizhi-rollout-train-deploy-experiment/env.sh
#
# If only one credential pair is provided, this script forwards it to the
# missing qz variables so `qz login` can still see a complete credential set.

if [ -n "${QZ_API_USERNAME:-}" ] && [ -z "${QZ_COOKIE_USERNAME:-}" ]; then
  export QZ_COOKIE_USERNAME="${QZ_API_USERNAME}"
fi

if [ -n "${QZ_API_PASSWORD:-}" ] && [ -z "${QZ_COOKIE_PASSWORD:-}" ]; then
  export QZ_COOKIE_PASSWORD="${QZ_API_PASSWORD}"
fi

if [ -n "${QZ_COOKIE_USERNAME:-}" ] && [ -z "${QZ_API_USERNAME:-}" ]; then
  export QZ_API_USERNAME="${QZ_COOKIE_USERNAME}"
fi

if [ -n "${QZ_COOKIE_PASSWORD:-}" ] && [ -z "${QZ_API_PASSWORD:-}" ]; then
  export QZ_API_PASSWORD="${QZ_COOKIE_PASSWORD}"
fi

export QZ_API_USERNAME="253108120151"
export QZ_API_PASSWORD="Jmhjc20030408#"
export QZ_COOKIE_USERNAME="253108120151"
export QZ_COOKIE_PASSWORD="jmhjc20030408#"
