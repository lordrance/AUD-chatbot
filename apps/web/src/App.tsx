/**
 * 应用壳：BrowserRouter、各研究流程页面路由与全站页脚。
 */
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LandingPage } from "./pages/LandingPage";
import { ConsentPage } from "./pages/ConsentPage";
import { EligibilityPage } from "./pages/EligibilityPage";
import { BaselinePage } from "./pages/BaselinePage";
import { RandomizePage } from "./pages/RandomizePage";
import { ChatPage } from "./pages/ChatPage";
import { PostSurveyPage } from "./pages/PostSurveyPage";
import { ThankYouPage } from "./pages/ThankYouPage";
import { IneligiblePage } from "./pages/IneligiblePage";
import { SafetyEndPage } from "./pages/SafetyEndPage";
import { ChatSummaryPage } from "./pages/ChatSummaryPage";
import { FollowUpPage } from "./pages/FollowUpPage";

/** 根组件：声明式路由表与全站页脚。 */
export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/consent" element={<ConsentPage />} />
          <Route path="/eligibility" element={<EligibilityPage />} />
          <Route path="/baseline" element={<BaselinePage />} />
          <Route path="/randomize" element={<RandomizePage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat-summary" element={<ChatSummaryPage />} />
          <Route path="/post-survey" element={<PostSurveyPage />} />
          <Route path="/follow-up/:token" element={<FollowUpPage />} />
          <Route path="/thank-you" element={<ThankYouPage />} />
          <Route path="/ineligible" element={<IneligiblePage />} />
          <Route path="/safety-end" element={<SafetyEndPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <footer className="site-footer">
          <p className="muted small">
            SafeChat-AUD · research instrument · not a medical product · single-session text · not continuously
            monitored
          </p>
        </footer>
      </div>
    </BrowserRouter>
  );
}
