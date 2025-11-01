#!/usr/bin/env node

const axios = require('axios');

async function testLocalChart() {
  console.log('🧪 开始测试本地图表生成...\n');
  
  try {
    // 测试数据
    const testData = {
      type: "line",
      data: [
        { time: "2025-01", value: 100 },
        { time: "2025-02", value: 200 },
        { time: "2025-03", value: 150 },
        { time: "2025-04", value: 300 },
        { time: "2025-05", value: 250 }
      ],
      title: "本地测试折线图",
      width: 800,
      height: 600,
      theme: "default"
    };

    console.log('📊 测试数据:');
    console.log(JSON.stringify(testData, null, 2));
    console.log('\n🔄 发送请求到本地渲染服务...');

    // 调用本地渲染服务
    const response = await axios.post('http://localhost:3000/api/gpt-vis', testData, {
      headers: {
        'Content-Type': 'application/json'
      },
      timeout: 10000
    });

    console.log('\n✅ 渲染成功！');
    console.log('📋 响应数据:');
    console.log(JSON.stringify(response.data, null, 2));

    if (response.data.success) {
      console.log('\n🎉 本地图表渲染服务工作正常！');
      console.log('💡 现在你可以在 AI 客户端中使用这个本地服务了');
    } else {
      console.log('\n❌ 渲染失败:', response.data.errorMessage);
    }

  } catch (error) {
    console.error('\n❌ 测试失败:');
    if (error.code === 'ECONNREFUSED') {
      console.error('🔌 无法连接到本地渲染服务 (http://localhost:3000)');
      console.error('💡 请确保渲染服务正在运行');
    } else {
      console.error('📝 错误详情:', error.message);
    }
  }
}

// 运行测试
testLocalChart();
