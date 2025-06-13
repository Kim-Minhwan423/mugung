// 완전 최소한의 디버그 코드
const { TalkClient } = require('node-kakao');
const client = new TalkClient();

const email = 'cook7179@naver.com';
const password = 'q1070619';

// 전역 예외 감지
process.on('unhandledRejection', (reason) => {
  console.error('🚨 전역 unhandledRejection 발생:', reason);
  if (reason instanceof Error) {
    console.error('📛 메시지:', reason.message);
    console.error('📄 스택:', reason.stack);
  } else {
    console.error('📦 상세:', JSON.stringify(reason, null, 2));
  }
});

(async () => {
  console.log('🔑 로그인 시도...');
  const result = await client.login(email, password);
  console.log('🟢 로그인 응답:', result);
})();
