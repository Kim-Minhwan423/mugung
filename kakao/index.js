// 완전한 디버그 추적용 코드
const { TalkClient } = require('node-kakao');
const client = new TalkClient();

const email = 'cook7179@naver.com';
const password = 'q1070619';

process.on('unhandledRejection', (reason) => {
  console.error('🚨 전역 unhandledRejection 발생:', reason);

  if (reason && typeof reason === 'object') {
    try {
      const keys = Object.getOwnPropertyNames(reason);
      console.error('📌 reason 속성들:', keys);
      for (const key of keys) {
        console.error(`   - ${key}:`, reason[key]);
      }
    } catch (parseErr) {
      console.error('⚠️ reason 객체 속성 분석 실패:', parseErr);
    }
  } else {
    console.error('📦 reason 값:', reason);
  }
});

(async () => {
  console.log('🔑 [1] 로그인 시도...');
  const result = await client.login(email, password);
  console.log('🟢 [2] 로그인 응답:', result);
})();
