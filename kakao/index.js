const { TalkClient } = require('node-kakao');

const client = new TalkClient();

const email = 'cook7179@naver.com';  // ← 여기에 봇 계정 이메일
const password = 'q1070619';              // ← 여기에 비밀번호

client.login(email, password).then(async (result) => {
  if (!result.success) {
    console.error('❌ 로그인 실패:', result.status);
    return;
  }

  console.log('✅ 로그인 성공');

  const channels = await client.channelList.all();
  const targetChannel = channels[무궁]; // 채팅방 이름

  if (targetChannel) {
    await targetChannel.sendChat('📦 [무궁] 재고 자동 발주 메시지 테스트');
    console.log('📨 메시지 전송 완료');
  } else {
    console.log('⚠️ 채팅방을 찾을 수 없습니다.');
  }
});
