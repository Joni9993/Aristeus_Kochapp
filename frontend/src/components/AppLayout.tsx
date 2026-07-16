import { Outlet } from 'react-router-dom'
import BottomNav from './BottomNav'

export default function AppLayout() {
  return (
    <>
      {/* Reserve enough space for the fixed BottomNav, including its own
          safe-area padding on notched phones (iOS home indicator). */}
      <div style={{ paddingBottom: 'calc(6rem + env(safe-area-inset-bottom))' }}>
        <Outlet />
      </div>
      <BottomNav />
    </>
  )
}
