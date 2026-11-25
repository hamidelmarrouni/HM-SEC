export const ENV = {
   NODE_ENV: (process.env.NODE_ENV || 'development') as 'production' | 'development',
   SERVER_PORT: process.env.PORT || '3006',
   ACCESS_TOKEN_SECRET: process.env.accessTokenSecret,
   REFRESH_TOKEN_SECRET: process.env.refreshTokenSecret,
   SMTP_HOST: process.env.SMTP_HOST || '127.0.0.1',
   SMTP_PORT: process.env.SMTP_PORT || '1025',
   SMTP_SERVICE: process.env.SMTP_SERVICE || '',
   SMTP_MAIL: process.env.SMTP_MAIL || 'hmsec@local.test',
   SMTP_PASSWORD: process.env.SMTP_PASSWORD || '',
} as const;

function checkEnv() {
   const required = ['ACCESS_TOKEN_SECRET', 'REFRESH_TOKEN_SECRET', 'SMTP_HOST', 'SMTP_PORT'] as const;
   const missing = required.filter((key) => !ENV[key]);
   if (missing.length > 0) {
      missing.forEach((key) => console.error(`${key} not found in environment`));
      throw new Error('Required environment variables missing');
   }
}
export default checkEnv;
