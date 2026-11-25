export const ENV = {
   NODE_ENV: (process.env.NODE_ENV || 'development') as 'production' | 'development',
   SERVER_PORT: process.env.PORT || '3008',
   POSTGRES_URI: process.env.POSTGRES_URI,
   USER_SERVICE_BASE_URL: process.env.USER_SERVICE_BASE_URL || 'http://127.0.0.1:3001',
   CHAT_REWARED_COOLOFF_INTERFVAL: process.env.CHAT_REWARED_COOLOFF_INTERFVAL ?? '86400000',
   ELASTICSEARCH_PROXY_BASE_URL:
      process.env.ELASTICSEARCH_PROXY_BASE_URL || 'http://127.0.0.1:3009',
};

function checkEnv() {
   if (!ENV.POSTGRES_URI) {
      console.error('POSTGRES_URI not found in environment');
      throw new Error('Required environment variables missing');
   }
}
export default checkEnv;
