#!/bin/bash
cd "$(dirname "$0")/frontend"
bun install
bun run build
