export const ENV = {
   NODE_ENV: (process.env.NODE_ENV || 'development') as 'production' | 'development',
   SERVER_PORT: process.env.PORT || '3004',
   MONGODB_URI: process.env.MONGODB_URI,
   ELASTICSEARCH_PROXY_BASE_URL:
      process.env.ELASTICSEARCH_PROXY_BASE_URL || 'http://127.0.0.1:3009',
   AWS_CLOUDFRONT_DISTRIBUTION_DOMAIN_NAME:
      process.env.AWS_CLOUDFRONT_DISTRIBUTION_DOMAIN_NAME || 'http://127.0.0.1:9000/hm-sec-media',
   KAFKA_CLIENT_ID: process.env.KAFKA_CLIENT_ID || 'hmsec-chat-service',
   KAFKA_BROKER_URI: process.env.KAFKA_BROKER_URI || '127.0.0.1:9092',
} as const;

function checkEnv() {
   const required = ['MONGODB_URI'] as const;
   const missing = required.filter((key) => !ENV[key]);
   if (missing.length > 0) {
      missing.forEach((key) => console.error(`${key} not found in environment`));
      throw new Error('Required environment variables missing');
   }
}
export default checkEnv;
