const { TalkClient } = require('node-kakao');

console.log('🔧 모듈 불러오기 완료');

const client = new TalkClient();

const email = 'cook7179@naver.com';
const password = 'q1070619';

console.log('📌 이메일, 비밀번호 변수 설정 완료');

async function startBot() {
  try {
    console.log('🚀 1. 로그인 시도 중...');
    const loginResult = await client.login(email, password);

    console.log('🟢 2. 로그인 결과:', loginResult);

    if (!loginResult.success) {
      console.error('❌ 3. 로그인 실패:', loginResult.status);
      return;
    }

    console.log('✅ 4. 로그인 성공');

    console.log('🔄 5. 채널 리스트 요청 중...');
    const channels = await client.channelList.all();
    console.log(`📋 6. 참여 중 채널 수: ${channels.length}`);

    for (const channel of channels) {
      console.log(`   - 채널 이름: ${channel.info.name}`);
    }

    console.log('🔍 7. "무궁" 포함 채널 탐색 중...');
    const targetChannel = channels.find(c => c.info.name.includes('무궁'));

    if (!targetChannel) {
      console.log('⚠️ 8. "무궁" 채널을 찾을 수 없습니다.');
      return;
    }

    console.log('📤 9. 메시지 전송 중...');
    await targetChannel.sendChat('[무궁] 📦 재고 자동 발주 테스트 메시지입니다.');
    console.log('✅ 10. 메시지 전송 완료');

  } catch (error) {
    console.error('🔥 예외 발생:', error);
    console.error('📛 예외 상세:', JSON.stringify(error, null, 2));
  }
}

console.log('🧠 startBot 실행');
startBot();
