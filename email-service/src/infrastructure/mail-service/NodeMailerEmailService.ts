import ejs from 'ejs';
import nodeMailer from 'nodemailer';
import path from 'path';
import { IEmailService } from '@ports/IEmailService';
import { logger } from '@config/logger';

export class NodeMailerEmailService implements IEmailService {
   private transporter = nodeMailer.createTransport({
      host: process.env.SMTP_HOST || '127.0.0.1',
      port: parseInt(process.env.SMTP_PORT || '1025'),
      secure: false,
      ...(process.env.SMTP_AUTH === 'true'
         ? {
              auth: {
                 user: process.env.SMTP_MAIL,
                 pass: process.env.SMTP_PASSWORD,
              },
           }
         : {}),
   });

   constructor() {}

   send = async (
      email: string,
      subject: string,
      data: any,
      template: string
   ): Promise<{ ack: boolean }> => {
      try {
         if (process.env.HMSEC_EMAIL_CONSOLE === 'true') {
            console.log(
               `[HM_SEC email] to=${email} subject=${subject} data=${JSON.stringify(data)}`
            );
            return { ack: true };
         }

         const templatePath = path.join(__dirname, './mails/', template);
         const html: string = await ejs.renderFile(templatePath, data);

         const mailOptions = {
            from: process.env.SMTP_MAIL || 'hmsec@local.test',
            to: email,
            subject,
            html,
         };

         await this.transporter.sendMail(mailOptions);
         return { ack: true };
      } catch (error) {
         logger.error('error while sending mail', { error });
         return { ack: false };
      }
   };
}
