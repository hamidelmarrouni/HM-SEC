export const ENV = {
   NODE_ENV: (process.env.NODE_ENV || 'development') as 'production' | 'development',
   SERVER_PORT: process.env.PORT || '3001',
   PASSWORD_SALT: process.env.passwordSalt || '10',
   OTP_SALT: process.env.otpSalt || '5',
   ACCESS_TOKEN_SECRET: process.env.accessTokenSecret,
   REFRESH_TOKEN_SECRET: process.env.refreshTokenSecret,
   RESET_PASSWORD_SECRET: process.env.resetPasswordTokenSecret,
   GOOGLE_CLIENT_ID: process.env.GOOGLE_CLIENT_ID || 'hmsec-local-disabled',
   GOOGLE_CLIENT_SECRET: process.env.GOOGLE_CLIENT_SECRET || 'hmsec-local-disabled',
   AWS_ACCESS_KEY: process.env.AWS_ACCESS_KEY || 'hmsec',
   AWS_SECRET_KEY: process.env.AWS_SECRET_KEY || 'hmsec-local-secret',
   AWS_REGION: process.env.AWS_REGION || 'us-east-1',
   AWS_S3_BUCKET_NAME: process.env.AWS_S3_BUCKET_NAME || 'hm-sec-media',
   AWS_CLOUDFRONT_DISTRIBUTION_DOMAIN_NAME:
      process.env.AWS_CLOUDFRONT_DISTRIBUTION_DOMAIN_NAME || 'http://127.0.0.1:9000/hm-sec-media',
   ELASTICSEARCH_PROXY_BASE_URL:
      process.env.ELASTICSEARCH_PROXY_BASE_URL || 'http://127.0.0.1:3009',
} as const;

function checkEnv() {
   const required = ['ACCESS_TOKEN_SECRET', 'REFRESH_TOKEN_SECRET', 'RESET_PASSWORD_SECRET'] as const;
   const missing = required.filter((key) => !ENV[key]);
   console.log('Node Env:', ENV.NODE_ENV);
   if (missing.length > 0) {
      missing.forEach((key) => console.error(`${key} not found in environment`));
      throw new Error('Required environment variables missing');
   }
}
export default checkEnv;
