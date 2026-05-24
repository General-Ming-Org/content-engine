import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { AUTH_EXPIRED_EVENT } from "../lib/auth";

/** Soft redirect when the API reports an expired session (avoids full-page reload flicker). */
export function AuthExpiredListener() {
  const navigate = useNavigate();

  useEffect(() => {
    function onExpired() {
      if (!window.location.pathname.startsWith("/login")) {
        navigate("/login", { replace: true });
      }
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [navigate]);

  return null;
}
