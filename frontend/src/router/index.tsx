import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from '../components/layout/AppShell';
import Flags from '../pages/Flags';
import ListingDetail from '../pages/ListingDetail';
import Listings from '../pages/Listings';
import Login from '../pages/Login';
import Sources from '../pages/Sources';
import { RequireAuth, RequirePermission } from './guards';

function Protected({ permission, children }: { permission: string; children: React.ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>
        <RequirePermission permission={permission}>{children}</RequirePermission>
      </AppShell>
    </RequireAuth>
  );
}

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Navigate to="/listings" replace />} />
      <Route
        path="/listings"
        element={
          <Protected permission="listing:read">
            <Listings />
          </Protected>
        }
      />
      <Route
        path="/listings/:listingId"
        element={
          <Protected permission="listing:read">
            <ListingDetail />
          </Protected>
        }
      />
      <Route
        path="/flags"
        element={
          <Protected permission="flag:read">
            <Flags />
          </Protected>
        }
      />
      <Route
        path="/sources"
        element={
          <Protected permission="source:read">
            <Sources />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/listings" replace />} />
    </Routes>
  );
}
