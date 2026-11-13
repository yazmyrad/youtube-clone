import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ChannelPage } from "./pages/ChannelPage";
import { HistoryPage } from "./pages/HistoryPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PlaylistPage } from "./pages/PlaylistPage";
import { RegisterPage } from "./pages/RegisterPage";
import { SearchPage } from "./pages/SearchPage";
import { SubscriptionsPage } from "./pages/SubscriptionsPage";
import { UploadPage } from "./pages/UploadPage";
import { WatchPage } from "./pages/WatchPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="/results" element={<SearchPage />} />
        <Route path="/feed/subscriptions" element={<SubscriptionsPage />} />
        <Route path="/feed/history" element={<HistoryPage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/watch" element={<WatchPage />} />
        <Route path="/:handle/:tab?" element={<ChannelPage />} />
        <Route path="/playlist" element={<PlaylistPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
