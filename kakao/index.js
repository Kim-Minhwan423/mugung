const { TalkClient } = require('node-kakao');

const client = new TalkClient();

const email = 'cook7179@naver.com';    // 여기에 실제 계정
const password = 'q1070619';          // 여기에 실제 비밀번호

async function startBot() {
  try {
    const loginResult = await client.login(email, password);

    if (!loginResult.success) {
      console.error('❌ 로그인 실패:', loginResult.status);
      return;
    }

    console.log('✅ 로그인 성공!');

    const channels = await client.channelList.all();
    const targetChannel = channels.find(channel =>
      channel.info.name.includes('무궁')
    );

    if (targetChannel) {
      await targetChannel.sendChat('[무궁] 📦 재고 자동 발주 테스트 메시지입니다.');
      console.log('✅ 메시지 전송 완료');
    } else {
      console.log('⚠️ "무궁" 단톡방을 찾지 못했습니다.');
    }

  } catch (error) {
    console.error('🔥 예외 발생:', error);
  }
}

startBot();
