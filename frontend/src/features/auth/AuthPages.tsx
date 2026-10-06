import { Link, Navigate, useSearchParams } from "react-router";

import { useLogIn, useSession, useSignUp } from "../../api/session";
import { nextParam, safeNext } from "../../lib/safeNext";
import { AuthForm } from "./AuthForm";

// Once signed in (including right after a successful submit), each page redirects to ?next=.

function useNext() {
  const [params] = useSearchParams();
  return safeNext(params.get("next"));
}

export function LoginPage() {
  const next = useNext();
  const session = useSession();
  const logIn = useLogIn();

  if (session.data) return <Navigate to={next} replace />;
  return (
    <AuthForm
      mode="login"
      title="Sign in"
      subtitle="Pick up where you left off with your serve history."
      submitLabel="Sign in"
      pendingLabel="Signing in…"
      pending={logIn.isPending}
      error={logIn.error}
      onSubmit={(email, password) => logIn.mutate({ email, password })}
      footer={
        <>
          <Link to="/forgot-password" className="font-medium text-accent underline">Forgot your password?</Link>
          <br />
          New here?{" "}
          <Link to={`/signup${nextParam(next)}`} className="font-medium text-accent underline">Create an account</Link>
        </>
      }
    />
  );
}

export function SignupPage() {
  const next = useNext();
  const session = useSession();
  const signUp = useSignUp();

  if (session.data) return <Navigate to={next} replace />;
  return (
    <AuthForm
      mode="signup"
      title="Create your account"
      subtitle="Your analyses are saved to your account, so you can track your serve over time."
      submitLabel="Create account"
      pendingLabel="Creating account…"
      pending={signUp.isPending}
      error={signUp.error}
      onSubmit={(email, password) => signUp.mutate({ email, password, accept_terms: true })}
      footer={
        <>
          Already have an account?{" "}
          <Link to={`/login${nextParam(next)}`} className="font-medium text-accent underline">Sign in</Link>
        </>
      }
    />
  );
}
