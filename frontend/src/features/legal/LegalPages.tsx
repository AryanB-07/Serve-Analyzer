import type { ReactNode } from "react";
import { Link } from "react-router";

import { HAS_PLACEHOLDERS, LAST_UPDATED, LEGAL } from "./config";

function Document({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="mx-auto w-full max-w-2xl space-y-6 py-4 leading-relaxed">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-ink-muted">Last updated {LAST_UPDATED}</p>
      </header>
      {HAS_PLACEHOLDERS && import.meta.env.DEV && (
        <p role="note" className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-sm text-warn">
          Development note: fill in the bracketed details in src/features/legal/config.ts before launch.
        </p>
      )}
      {children}
    </article>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

const list = "list-disc space-y-1.5 pl-5";
const contact = <span className="font-medium">{LEGAL.contactEmail}</span>;

export function PrivacyPage() {
  const days = LEGAL.uploadRetentionDays;
  return (
    <Document title="Privacy Policy">
      <p>
        Serve Analyzer is run by {LEGAL.operator} ("we"). This policy explains what we collect when you use it, why,
        how long we keep it, and how to delete it. In short: we use your videos only to analyze your serve, we don't
        sell or share them, and you can delete them at any time.
      </p>

      <Section title="What we collect">
        <ul className={list}>
          <li>
            <strong>Your account:</strong> your email address, your password (stored only as a one-way argon2 hash, so we
            can't read it), when you signed up, whether you've confirmed your email, and which version of these terms you
            accepted.
          </li>
          <li>
            <strong>Videos you upload</strong> and what we compute from them: body joint positions in each frame, joint
            angles, the serve's phases, your results and feedback, a thumbnail, and two processed copies of the video (one
            for playback and one with the skeleton drawn on).
          </li>
          <li>
            <strong>Sign-in and security records:</strong> a session cookie that keeps you signed in, and short-lived
            records of sign-in attempts used to stop password guessing. The attempt records store your IP address and
            email only as one-way hashes.
          </li>
          <li>
            <strong>Error logs</strong> from our servers, which record what went wrong with an analysis. We don't keep a
            log of every request or of visitors' IP addresses.
          </li>
          <li>
            <strong>On your device:</strong> your light or dark theme choice, saved in your browser's local storage.
          </li>
        </ul>
      </Section>

      <Section title="What we don't do">
        <ul className={list}>
          <li>No advertising, analytics or tracking scripts. The app loads nothing from other companies' servers.</li>
          <li>We don't sell, rent or share your personal information or videos.</li>
          <li>We don't use your videos to train machine-learning models.</li>
          <li>
            We don't identify people. The analysis estimates where joints are so it can measure technique. It doesn't use
            face recognition and doesn't try to work out who anyone is.
          </li>
        </ul>
      </Section>

      <Section title="How we use it">
        <ul className={list}>
          <li>To analyze your serve and show you the results and your history.</li>
          <li>To run your account: signing in, confirming your email, resetting your password.</li>
          <li>To keep the service secure and working: rate limits, fixing errors, preventing abuse.</li>
          <li>
            To email you about your account only: confirmation and reset links, and notices when your password changes or
            your account is deleted. No newsletters or marketing.
          </li>
        </ul>
        <p>
          Your video is analyzed on our own servers. It isn't sent to any third-party AI service.
        </p>
      </Section>

      <Section title="Who else handles it">
        <p>
          We use a small number of service providers, who process data only on our behalf and under their own security
          obligations:
        </p>
        <ul className={list}>
          <li>Our cloud hosting provider (servers, database and file storage), in {LEGAL.hostingRegion}.</li>
          <li>Our email delivery provider, which sends account emails to your address.</li>
        </ul>
        <p>We may disclose information if the law requires it, for example in response to a valid court order.</p>
      </Section>

      <Section title="How long we keep it">
        <ul className={list}>
          <li>
            <strong>Original uploaded videos:</strong> deleted automatically {days} days after upload. Your results,
            including their own playback copy, stay until you delete them. After {days} days a failed analysis can't be
            retried; upload the video again instead.
          </li>
          <li>
            <strong>Results and your account:</strong> until you delete them.
          </li>
          <li>
            <strong>Uploads that never finished:</strong> deleted after 1 day.
          </li>
          <li>
            <strong>Sessions:</strong> end 30 days after you were last active, or when you sign out.
          </li>
          <li>
            <strong>Emailed links:</strong> stop working after 1 hour (password reset) or 24 hours (email confirmation),
            and are deleted soon after.
          </li>
          <li>
            <strong>Sign-in attempt records:</strong> 1 day.
          </li>
          <li>
            <strong>Server logs:</strong> rotated automatically and kept only briefly.
          </li>
          <li>
            <strong>Backups:</strong> our database is backed up automatically. Deleted information can remain in backups
            for up to {LEGAL.backupRetentionDays} days before it's overwritten.
          </li>
        </ul>
      </Section>

      <Section title="Your choices and rights">
        <ul className={list}>
          <li>
            <strong>Delete an analysis</strong> from your history or its results page. This deletes the video and results
            right away.
          </li>
          <li>
            <strong>Delete your account</strong> from your <Link to="/account" className="text-accent underline">account
            page</Link>. This deletes your account and every video and analysis in it right away.
          </li>
          <li>
            <strong>Get a copy, correct, or ask about your data</strong> by emailing {contact}. We'll respond within 30
            days.
          </li>
        </ul>
        <p>
          Depending on where you live (for example under the GDPR in the EU and UK, or the CCPA in California), you may
          have further rights, such as to object to processing or to complain to your data protection authority. We'll
          honor them. We process your information to provide the service you asked for (performing our contract with you)
          and, for security, in our legitimate interest in keeping the service safe.
        </p>
      </Section>

      <Section title="Children and other people in your videos">
        <p>
          You must be at least {LEGAL.minimumAge} to create an account. If you're under 18, or under the age of digital
          consent where you live, use Serve Analyzer with a parent's or guardian's permission. We don't knowingly collect
          information from children under {LEGAL.minimumAge}. If you think a child has given us information, email{" "}
          {contact} and we'll delete it.
        </p>
        <p>
          Only upload videos of yourself, or of people who have agreed to it (a parent or guardian for a child). Coaches
          should get permission before uploading a player's serve.
        </p>
      </Section>

      <Section title="Security">
        <p>
          Everything travels over HTTPS. Passwords are hashed. Stored videos aren't public: they can only be viewed through
          short-lived links issued to your signed-in account. No system is perfectly secure, but if a breach affects your
          information we'll tell you as the law requires.
        </p>
      </Section>

      <Section title="Changes and contact">
        <p>
          If we change this policy in a way that matters, we'll update the date above and email you before the change
          takes effect. Questions or requests: {contact}.
        </p>
      </Section>
    </Document>
  );
}

export function TermsPage() {
  return (
    <Document title="Terms of Service">
      <p>
        These terms are an agreement between you and {LEGAL.operator} ("we") for using Serve Analyzer. By creating an
        account you agree to them and to our <Link to="/privacy" className="text-accent underline">Privacy Policy</Link>.
      </p>

      <Section title="Who can use it">
        <p>
          You must be at least {LEGAL.minimumAge}. If you're under 18, or under the age of digital consent where you
          live, you need a parent's or guardian's permission. Keep your password safe: you're responsible for what happens
          under your account.
        </p>
      </Section>

      <Section title="Your videos">
        <ul className={list}>
          <li>You keep ownership of everything you upload.</li>
          <li>
            You give us permission to store, process and display your videos and results only to provide the service to
            you, for as long as they're stored. This permission ends when you delete them.
          </li>
          <li>
            Only upload videos you have the right to use, of yourself or of people who agreed to it (a parent or guardian
            for a child).
          </li>
        </ul>
      </Section>

      <Section title="Acceptable use">
        <p>Don't use Serve Analyzer to:</p>
        <ul className={list}>
          <li>upload anything illegal, sexual, violent or hateful, or that invades someone's privacy;</li>
          <li>attack, overload, scrape or try to get around the service's security or usage limits;</li>
          <li>access other people's accounts or data;</li>
          <li>resell or rebrand the service without our written permission.</li>
        </ul>
        <p>We may remove content or suspend accounts that break these rules.</p>
      </Section>

      <Section title="What the analysis is, and isn't">
        <p>
          Serve Analyzer estimates body positions from a single video using computer vision, and compares them with
          general reference ranges. Estimates can be wrong, especially with unusual camera angles, poor lighting or
          clothing that hides joints. It isn't a coach, and it isn't medical or physiotherapy advice. If you have pain or
          an injury, see a qualified professional. Change your technique at your own risk.
        </p>
      </Section>

      <Section title="The service">
        <p>
          Serve Analyzer is currently free. We may change, limit or stop features, and we'll give reasonable notice before
          shutting the service down so you can save what you need. There are daily limits on how many serves you can
          analyze.
        </p>
      </Section>

      <Section title="Ending this agreement">
        <p>
          You can stop at any time by deleting your account, which deletes your data as described in the Privacy Policy.
          We may suspend or end your access if you seriously or repeatedly break these terms.
        </p>
      </Section>

      <Section title="Disclaimers and liability">
        <p>
          The service is provided "as is" and "as available", without warranties of any kind, to the extent the law
          allows. To the extent the law allows, we aren't liable for indirect or consequential losses, or for injuries
          from acting on the analysis. Our total liability for any claim is limited to $50. Nothing in these terms limits
          rights you have under consumer protection law that can't be waived.
        </p>
      </Section>

      <Section title="Changes, law and contact">
        <p>
          If we change these terms in a way that matters, we'll update the date above and email you before the change
          takes effect. Continuing to use the service after that means you accept the new terms. These terms are governed
          by the laws of {LEGAL.governingLaw}. Questions: {contact}.
        </p>
      </Section>
    </Document>
  );
}
