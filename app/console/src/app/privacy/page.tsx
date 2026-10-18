import type { Metadata } from "next";
import { LEGAL } from "@/lib/legal";
import styles from "../legal.module.css";

export const metadata: Metadata = { title: `Privacy policy, ${LEGAL.program}` };

// Privacy policy for the console and the text alert program. Written to cover what carriers check for SMS:
// what is collected, how phone numbers are used, and that numbers and consent are never shared for marketing.
export default function Privacy() {
  return (
    <main className={styles.doc}>
      <h1 className="title">Privacy policy</h1>
      <p className={styles.meta}>{LEGAL.program}, operated by {LEGAL.operator}. Effective {LEGAL.effective}.</p>

      <h2>What this covers</h2>
      <p>
        This policy covers the Holy-Crap console, its companion watch, and the {LEGAL.program} text messages. Holy-Crap watches
        poultry pens with a camera and alerts farm staff when droppings in a pen may need a look.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>Your mobile phone number and name, when you or your farm sign you up for text alerts.</li>
        <li>Your consent to receive texts, with the date, time and how it was given.</li>
        <li>Your replies to our texts, including STOP and HELP.</li>
        <li>Records of alerts and actions on the console, such as an alert acknowledged or a vet request.</li>
        <li>Camera images of pen floors. They show litter, droppings and birds, not people. Images are not linked to your phone number.</li>
      </ul>

      <h2>How we use it</h2>
      <ul>
        <li>To send the barn alerts you signed up for and the replies to your HELP and STOP messages.</li>
        <li>To keep a record of your consent and of opt-outs, so we never text you after you stop.</li>
        <li>To run, fix and improve the monitoring service.</li>
      </ul>
      <p>We do not sell personal information, and we do not use your phone number for advertising.</p>

      <h2>Sharing</h2>
      <p className={styles.key}>
        No mobile information will be shared with third parties or affiliates for marketing or promotional purposes.
        Text messaging opt-in data and consent will not be shared with any third parties.
      </p>
      <p>
        We share your phone number only with the service providers that deliver our text messages and host the service, and
        only so they can do that work for us. They may not use it for anything else. We may also disclose information when the law requires it.
      </p>

      <h2>How long we keep it</h2>
      <p>
        We keep your phone number and consent record while you are signed up, and for a limited time after you opt out so we
        can prove consent and honour the opt-out. Alert records are kept as long as the farm uses the service.
      </p>

      <h2>Security</h2>
      <p>We use reasonable technical measures to protect your information, such as encrypted connections and limited access.</p>

      <h2>Your choices</h2>
      <ul>
        <li>Reply STOP to any of our texts to stop receiving them.</li>
        <li>Email {LEGAL.email} to see, correct or delete the information we hold about you.</li>
      </ul>

      <h2>Children</h2>
      <p>The service is for farm staff and is not directed at children under 13.</p>

      <h2>Changes</h2>
      <p>If this policy changes, we will update this page and the effective date above.</p>

      <h2>Contact</h2>
      <p>{LEGAL.operator}, {LEGAL.email}</p>
    </main>
  );
}
