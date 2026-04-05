#!/bin/bash
# Cloudflare Pages 构建脚本
# 将 %API_BASE_URL% 占位符替换为实际的后端 API 地址
sed -i "s|%API_BASE_URL%|${API_BASE_URL:-}|g" static/index.html
