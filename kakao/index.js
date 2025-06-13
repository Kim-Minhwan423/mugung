// index.js (절대 에러 안 놓치는 디버깅용)
process.on('unhandledRejection', (reason, promise) => {
  console.error('🚨 전역 unhandledRejection 감지:', reason);
});

process.on('uncaughtException', (err) => {
  console.error('🚨 전역 uncaughtException 감지:', err);
});

console.log('✅ [0] 시작됨 - 모듈 불러오기');

const { TalkClient } = require('node-kakao');
const client = new TalkClient();

const email = 'your_email@example.com';
const password = 'your_password';

console.log('✅ [1] 이메일/비번 설정 완료');

async function startBot() {
  console.log('🔄 [2] startBot 진입');
  try {
    console.log('🔑 [3] 로그인 시도 중...');
    const loginResult = await client.login(email, password);

    console.log('🟢 [4] 로그인 결과:', loginResult);

    if (!loginResult.success) {
      console.error('❌ [5] 로그인 실패:', loginResult.status);
      return;
    }

    console.log('✅ [6] 로그인 성공');

    const channels = await client.channelList.all();
    console.log(`📋 [7] 채널 수: ${channels.length}`);

    for (const c of channels) {
      console.log('📌 채널명:', c.info.name);
    }

    const targetChannel = channels.find(c => c.info.name.includes('무궁'));

    if (!targetChannel) {
      console.log('⚠️ [8] "무궁" 채널 없음');
      return;
    }

    console.log('📤 [9] 메시지 전송 중...');
    await targetChannel.sendChat('[무궁] 📦 자동 발주 테스트');
    console.log('✅ [10] 메시지 전송 완료');
  } catch (err) {
    console.error('🔥 [X] 내부 catch 오류:', err);
  }
}

startBot();
