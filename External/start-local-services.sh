#!/bin/bash

echo "🚀 启动 MCP Server Chart 本地服务..."

# 检查是否已有服务在运行
if pgrep -f "node server.js" > /dev/null; then
    echo "⚠️  本地渲染服务已在运行"
else
    echo "📊 启动本地渲染服务..."
    cd GPT-Vis/gpt-vis-server
    node server.js &
    cd ../..
    sleep 2
    echo "✅ 本地渲染服务已启动 (http://localhost:3000)"
fi

# 设置环境变量
export VIS_REQUEST_SERVER=http://localhost:3000/api/gpt-vis
echo "🔧 环境变量已设置: VIS_REQUEST_SERVER=$VIS_REQUEST_SERVER"

# 测试服务
echo "🧪 测试本地渲染服务..."
if curl -s http://localhost:3000/health | grep -q "ok"; then
    echo "✅ 本地渲染服务正常"
else
    echo "❌ 本地渲染服务异常"
    exit 1
fi

echo ""
echo "🎉 所有服务已就绪！"
echo ""
echo "📋 使用说明："
echo "1. 在 AI 客户端中配置 MCP Server:"
echo "   VIS_REQUEST_SERVER=http://localhost:3000/api/gpt-vis"
echo ""
echo "2. 或者手动启动 MCP Server:"
echo "   cd mcp-server-chart"
echo "   export VIS_REQUEST_SERVER=http://localhost:3000/api/gpt-vis"
echo "   npx @antv/mcp-server-chart --transport sse"
echo ""
echo "3. 查看完整使用指南:"
echo "   cat 本地使用指南.md"
echo ""
echo "🔗 服务地址:"
echo "   - 本地渲染服务: http://localhost:3000"
echo "   - 健康检查: http://localhost:3000/health"
