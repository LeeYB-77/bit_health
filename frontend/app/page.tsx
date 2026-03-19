'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getGymStatus, GymStatus, getUserDashboard, UserDashboardStats } from '@/lib/api';
import { Activity, MapPin, LogOut, ChevronRight, BarChart3, Settings } from 'lucide-react';
import Image from 'next/image';

export default function Home() {
  const router = useRouter();
  const [gymStatus, setGymStatus] = useState<GymStatus | null>(null);
  const [dashboardStats, setDashboardStats] = useState<UserDashboardStats>({ monthly_count: 0, has_today_reservation: false });
  const [userName, setUserName] = useState('');
  const [userRole, setUserRole] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    const name = localStorage.getItem('user_name');

    if (!token) {
      router.push('/login');
      return;
    }

    setUserName(name || '회원');
    setUserRole(localStorage.getItem('user_role') || 'user');
    fetchStatus();
  }, [router]);

  const fetchStatus = async () => {
    try {
      const statusData = await getGymStatus();
      setGymStatus(statusData);

      const dashboardData = await getUserDashboard();
      setDashboardStats(dashboardData);
    } catch (error) {
      console.error('Failed to load status', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_role');
    router.push('/login');
  };

  const getCongestionColor = (level: string) => {
    switch (level) {
      case 'low': return { bg: 'bg-emerald-500', text: '여유', label: 'bg-emerald-50 text-emerald-600 border-emerald-100' };
      case 'medium': return { bg: 'bg-yellow-400', text: '보통', label: 'bg-yellow-50 text-yellow-600 border-yellow-100' };
      case 'high': return { bg: 'bg-rose-500', text: '혼잡', label: 'bg-rose-50 text-rose-500 border-rose-100' };
      default: return { bg: 'bg-gray-300', text: '-', label: 'bg-gray-50 text-gray-400 border-gray-100' };
    }
  };

  if (loading) return (
    <div className="h-screen flex items-center justify-center bg-gray-50">
      <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
    </div>
  );

  const congestion = getCongestionColor(gymStatus?.congestion || 'low');

  return (
    <div className="h-screen flex flex-col bg-gray-50 font-sans text-gray-900 overflow-hidden">

      {/* Header - compact */}
      <header className="bg-white border-b border-gray-100 shrink-0">
        <div className="max-w-lg mx-auto px-4 h-12 flex items-center justify-between">
          <Image src="/logo.svg" alt="BIT Wellness Center" width={80} height={24} className="h-6 w-auto" />
          <div className="flex items-center gap-1">
            {userRole === 'admin' && (
              <button
                onClick={() => router.push('/admin')}
                className="p-1.5 text-gray-400 hover:text-blue-600 transition-colors flex items-center gap-1"
                title="관리자 페이지"
              >
                <Settings size={16} />
                <span className="text-xs font-medium">관리자</span>
              </button>
            )}
            <button
              onClick={handleLogout}
              className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </header>

      {/* Main - grows to fill remaining height */}
      <main className="flex-1 max-w-lg mx-auto w-full px-4 py-3 flex flex-col gap-3 min-h-0">

        {/* Welcome */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              안녕하세요, <span className="text-blue-600">{userName}</span>님 👋
            </h1>
            <p className="text-gray-400 text-sm mt-0.5">오늘도 건강한 하루 되세요!</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-400">이번 달 운동</p>
            <p className="text-2xl font-bold text-purple-600">{dashboardStats.monthly_count}<span className="text-sm text-gray-400 font-normal ml-0.5">회</span></p>
          </div>
        </div>

        {/* Gym Status Card */}
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 shrink-0">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="p-1.5 bg-blue-50 text-blue-600 rounded-lg">
                <Activity size={18} />
              </div>
              <span className="font-bold text-gray-800">헬스장 현황</span>
            </div>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${congestion.label}`}>
              {congestion.text}
            </span>
          </div>
          <div className="flex items-baseline gap-1.5 mb-2">
            <span className="text-3xl font-bold text-gray-900">{gymStatus?.count ?? 0}</span>
            <span className="text-gray-400 text-sm">/ {gymStatus?.capacity ?? 0}명</span>
          </div>
          <div className="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden">
            <div
              className={`${congestion.bg} h-full rounded-full transition-all duration-500`}
              style={{ width: `${Math.min(((gymStatus?.count || 0) / (gymStatus?.capacity || 100)) * 100, 100)}%` }}
            />
          </div>
        </div>

        {/* 2-column grid - fixed height, no stretch */}
        <div className="grid grid-cols-2 gap-3 shrink-0">
          {/* Golf Reservation */}
          <button
            onClick={() => router.push('/golf')}
            className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 text-left flex flex-col gap-3 active:scale-[0.97] transition-transform group"
          >
            <div className="p-1.5 bg-emerald-50 text-emerald-600 rounded-lg w-fit">
              <MapPin size={18} />
            </div>
            <div>
              <p className="font-bold text-gray-800">스크린골프</p>
              <p className="text-gray-400 text-sm mt-0.5">실시간 예약</p>
            </div>
          </button>

          {/* Monthly Stats */}
          <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 flex flex-col gap-3">
            <div className="p-1.5 bg-purple-50 text-purple-600 rounded-lg w-fit">
              <BarChart3 size={18} />
            </div>
            <div>
              <p className="font-bold text-gray-800">이번 달</p>
              <div className="flex items-baseline gap-1 mt-0.5">
                <span className="text-2xl font-bold text-purple-600">{dashboardStats.monthly_count}</span>
                <span className="text-sm text-gray-400">회 출석</span>
              </div>
            </div>
          </div>
        </div>

        {/* Today Banner */}
        <div className={`bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl px-4 py-3 text-white flex items-center justify-between shrink-0 ${dashboardStats.has_today_reservation ? 'ring-2 ring-indigo-200' : ''}`}>
          <div>
            <p className="font-bold text-sm">{dashboardStats.has_today_reservation ? '🏌️ 오늘 골프 예약이 있습니다!' : '💪 오늘도 화이팅!'}</p>
            <p className="text-indigo-200 text-xs mt-0.5">건강한 습관이 미래를 만듭니다.</p>
          </div>
        </div>

      </main>
    </div>
  );
}
