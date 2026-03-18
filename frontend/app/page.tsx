'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getGymStatus, GymStatus, getUserDashboard, UserDashboardStats } from '@/lib/api';
import { Activity, MapPin, LogOut, User, ChevronRight, BarChart3, Calendar } from 'lucide-react';
import Image from 'next/image';

export default function Home() {
  const router = useRouter();
  const [gymStatus, setGymStatus] = useState<GymStatus | null>(null);
  const [dashboardStats, setDashboardStats] = useState<UserDashboardStats>({ monthly_count: 0, has_today_reservation: false });
  const [userName, setUserName] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    const name = localStorage.getItem('user_name');

    if (!token) {
      router.push('/login');
      return;
    }

    setUserName(name || '회원');
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
      case 'low': return 'text-emerald-500 bg-emerald-50 border-emerald-100';
      case 'medium': return 'text-yellow-600 bg-yellow-50 border-yellow-100';
      case 'high': return 'text-rose-500 bg-rose-50 border-rose-100';
      default: return 'text-gray-500 bg-gray-50 border-gray-100';
    }
  };

  const getCongestionText = (level: string) => {
    switch (level) {
      case 'low': return '여유';
      case 'medium': return '보통';
      case 'high': return '혼잡';
      default: return '-';
    }
  };

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50 pb-24 font-sans text-gray-900">
      {/* Header */}
      <header className="bg-white sticky top-0 z-30 border-b border-gray-100 shadow-sm/50 backdrop-blur-md bg-white/80">
        <div className="max-w-lg mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Image src="/logo.svg" alt="BIT Wellness Center" width={100} height={28} className="h-7 w-auto" />
          </div>
          <button
            onClick={handleLogout}
            className="p-2 -mr-2 text-gray-400 hover:text-gray-600 transition-colors"
          >
            <LogOut size={20} />
          </button>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-6 py-8 space-y-8">

        {/* Welcome Section */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">안녕하세요, <br /><span className="text-blue-600">{userName}</span>님</h1>
            <p className="text-gray-500 text-sm mt-1">오늘도 건강한 하루 되세요!</p>
          </div>
          <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center text-blue-600">
            <User size={24} />
          </div>
        </div>

        {/* Status Dashboard */}
        <div className="grid grid-cols-2 gap-4">
          {/* Gym Card */}
          <div className="col-span-2 bg-white rounded-3xl p-6 shadow-sm border border-gray-100 relative group overflow-hidden">
            <div className="absolute top-0 right-0 p-6 opacity-5 group-hover:opacity-10 transition-opacity">
              <Activity size={80} />
            </div>

            <div className="relative z-10">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="p-2 bg-blue-50 text-blue-600 rounded-xl">
                    <Activity size={20} />
                  </div>
                  <h2 className="font-bold text-gray-800">헬스장 현황</h2>
                </div>
                <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getCongestionColor(gymStatus?.congestion || 'low')}`}>
                  {getCongestionText(gymStatus?.congestion || 'low')}
                </span>
              </div>

              <div className="flex items-end gap-2 mb-2">
                <span className="text-4xl font-bold text-gray-900">{gymStatus?.count}</span>
                <span className="text-gray-400 font-medium mb-1">/ {gymStatus?.capacity}명</span>
              </div>
              <div className="w-full bg-gray-100 h-2 rounded-full overflow-hidden">
                <div
                  className="bg-blue-500 h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(((gymStatus?.count || 0) / (gymStatus?.capacity || 100)) * 100, 100)}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* Golf Card */}
          <button
            onClick={() => router.push('/golf')}
            className="col-span-2 sm:col-span-1 bg-white rounded-3xl p-6 shadow-sm border border-gray-100 text-left transition-transform active:scale-[0.98] group"
          >
            <div className="flex items-start justify-between mb-8">
              <div className="p-2 bg-emerald-50 text-emerald-600 rounded-xl">
                <MapPin size={20} />
              </div>
              <div className="p-1.5 bg-gray-50 rounded-full text-gray-400 group-hover:bg-blue-50 group-hover:text-blue-500 transition-colors">
                <ChevronRight size={16} />
              </div>
            </div>
            <div>
              <h3 className="font-bold text-gray-800 text-lg">스크린골프</h3>
              <p className="text-gray-500 text-xs mt-1">실시간 예약하기</p>
            </div>
          </button>

          {/* My Record Card */}
          <div className="col-span-2 sm:col-span-1 bg-white rounded-3xl p-6 shadow-sm border border-gray-100 overflow-hidden relative">
            <div className="flex items-start justify-between mb-8">
              <div className="p-2 bg-purple-50 text-purple-600 rounded-xl">
                <BarChart3 size={20} />
              </div>
            </div>
            <div>
              <h3 className="font-bold text-gray-800 text-lg">이번 달 운동</h3>
              <div className="flex items-baseline gap-1 mt-1">
                <span className="text-2xl font-bold text-purple-600">{dashboardStats.monthly_count}</span>
                <span className="text-xs text-gray-500">회 출석 완료!</span>
              </div>
            </div>
          </div>
        </div>

        {/* Quick Links / Banner */}
        <div className={`bg-gradient-to-r from-indigo-500 to-purple-600 rounded-3xl p-6 text-white shadow-lg shadow-indigo-200 flex items-center justify-between ${dashboardStats.has_today_reservation ? 'animate-pulse ring-4 ring-indigo-200' : ''}`}>
          <div>
            <p className="font-bold text-lg mb-1">{dashboardStats.has_today_reservation ? '🏌️ 오늘 스크린골프 예약이 있습니다!' : '오늘도 화이팅!'}</p>
            <p className="text-indigo-100 text-xs">건강한 습관이 미래를 만듭니다.</p>
          </div>
          <Calendar className="text-white/80" size={32} />
        </div>

      </main>
    </div>
  );
}
