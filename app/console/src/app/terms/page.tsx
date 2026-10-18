import type { Metadata } from "next";
import { LEGAL } from "@/lib/legal";
import styles from "../legal.module.css";

export const metadata: Metadata = { title: `Terms, ${LEGAL.program}` };

// Program terms for the text alerts: what is sent, how often, how to stop and get help, as carriers require.
export default function Terms() {
  return (
    <main className={styles.doc}>
      <h1 className="title">Terms and conditions</h1>
      <p className={styles.meta}>{LEGAL.program}, operated by {LEGAL.operator}. Effective {LEGAL.effective}.</p>

      <h2>The program</h2>
      <p>
        {LEGAL.program} sends text messages to farm staff about the poultry pens they look after. Messages tell you when a pen
        may need attention, for example abnormal droppings found by the camera, a pen marked urgent, or a vet request made from
        the console or the watch. These are operational alerts only. We do not send marketing messages.
      </p>

      <h2>Signing up</h2>
      <p>
        You receive texts only after you have agreed to receive barn alerts on your mobile number, given directly to the team
        that runs the farm's monitoring. Consent is not a condition of any purchase, and you can withdraw it at any time by replying STOP.
      </p>

      <h2>How often</h2>
      <p>Message frequency varies with what happens in the barn, usually a few messages a week and up to several a day when a pen needs attention.</p>

      <h2>Costs</h2>
      <p className={styles.key}>Message and data rates may apply.</p>

      <h2>Stop and help</h2>
      <ul>
        <li>Reply <b>STOP</b> to any message to stop all texts. You will get one confirmation and nothing after that.</li>
        <li>Reply <b>START</b> to sign up again.</li>
        <li>Reply <b>HELP</b> for help, or email {LEGAL.email}.</li>
      </ul>

      <h2>Delivery</h2>
      <p>
        Carriers are not liable for delayed or undelivered messages. Alerts are a screening aid, not a diagnosis, and must not
        replace checking the birds and calling a vet when needed.
      </p>

      <h2>Privacy</h2>
      <p>How we handle your number and consent is described in our <a href="/privacy">privacy policy</a>.</p>

      <h2>Changes</h2>
      <p>We may update these terms. The current version is always on this page with its effective date.</p>

      <h2>Contact</h2>
      <p>Contact {LEGAL.operator} at {LEGAL.email}.</p>
    </main>
  );
}
