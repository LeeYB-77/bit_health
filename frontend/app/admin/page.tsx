'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer
} from 'recharts';
import { API_URL } from '@/lib/api';
import {
    Users,
    Dumbbell,
    Flag,
    ArrowRight,
    CalendarClock,
    Clock,
    Activity
} from 'lucide-react';

interface DashboardStats {
    total_users: number;
    current_gym_users: number;
    current_golf_users: number;
}

interface User {
    id: number;
    name: string;
    type: string;
    enter_time: string;
}

export default function AdminDashboard() {
    const [stats, setStats] = useState<DashboardStats>({ total_users: 0, current_gym_users: 0, current_golf_users: 0 });
    const [currentUsers, setCurrentUsers] = useState<User[]>([]);
    const [chartData, setChartData] = useState<any[]>([]);
    const [period, setPeriod] = useState<string>('this_week');
    const router = useRouter();

    useEffect(() => {
        fetchDashboardData();
        const interval = setInterval(fetchDashboardData, 10000); // Refresh every 10 seconds

        return () => clearInterval(interval);
    }, [period]);

    const fetchDashboardData = async () => {
        const token = localStorage.getItem('access_token');
        const headers = { 'Authorization': `Bearer ${token}` };

        try {
            const statsRes = await fetch(`${API_URL}/api/admin/dashboard/stats`, { headers });
            if (statsRes.ok) setStats(await statsRes.json());

            const usersRes = await fetch(`${API_URL}/api/admin/dashboard/current-users`, { headers });
            if (usersRes.ok) setCurrentUsers(await usersRes.json());

            const historyRes = await fetch(`${API_URL}/api/admin/dashboard/usage-history?period=${period}`, { headers });
            if (historyRes.ok) {
                const data = await historyRes.json();
                setChartData(data);
            }
        } catch (error) {
            console.error('Failed to fetch dashboard data', error);
        }
    };

    return (
        <div className="min-h-screen bg-gray-50 font-sans text-gray-900">
            {/* Header */}
            <div className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-10">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Activity className="text-blue-600" />
                        <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600">
                            BIT Wellness Center Admin
                        </span>
                    </div>
                    <div className="flex items-center gap-4">
                        {/* Logout or User Profile could go here */}
                    </div>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">

                {/* Welcome Section */}
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">대시보드</h1>
                    <p className="text-gray-500 mt-1">오늘의 센터 현황을 한눈에 확인하세요.</p>
                </div>

                {/* Top Cards Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {/* Gym Card */}
                    <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-2xl p-6 text-white shadow-lg shadow-blue-200 transform hover:scale-[1.02] transition-transform duration-200">
                        <div className="flex justify-between items-start">
                            <div>
                                <p className="text-blue-100 font-medium text-sm">현재 헬스장 이용자</p>
                                <div className="mt-3 flex items-baseline gap-2">
                                    <h3 className="text-4xl font-bold">{stats.current_gym_users}</h3>
                                    <span className="text-blue-200 text-sm">명</span>
                                </div>
                            </div>
                            <div className="p-3 bg-white/20 rounded-xl backdrop-blur-sm">
                                <Dumbbell className="text-white w-6 h-6" />
                            </div>
                        </div>
                        <div className="mt-4 pt-4 border-t border-white/20 flex items-center gap-2 min-h-[24px]">
                            {/* Additional info placeholder */}
                            <span className="text-xs text-blue-100 bg-blue-700/30 px-2 py-1 rounded">실시간 집계 중</span>
                        </div>
                    </div>

                    {/* Golf Card */}
                    <div className="bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-2xl p-6 text-white shadow-lg shadow-emerald-200 transform hover:scale-[1.02] transition-transform duration-200">
                        <div className="flex justify-between items-start">
                            <div>
                                <p className="text-emerald-100 font-medium text-sm">스크린골프 예약/이용</p>
                                <div className="mt-3 flex items-baseline gap-2">
                                    <h3 className="text-4xl font-bold">{stats.current_golf_users}</h3>
                                    <span className="text-emerald-200 text-sm">명</span>
                                </div>
                            </div>
                            <div className="p-3 bg-white/20 rounded-xl backdrop-blur-sm">
                                <Flag className="text-white w-6 h-6" />
                            </div>
                        </div>
                        <div className="mt-4 pt-4 border-t border-white/20 flex flex-col gap-2">
                            <button
                                onClick={() => router.push('/admin/golf')}
                                className="text-xs text-emerald-100 hover:text-white flex items-center gap-1 transition-colors"
                            >
                                예약 및 설정 관리 <ArrowRight size={12} />
                            </button>
                        </div>
                    </div>

                    {/* Management Card (Merged User & QR) */}
                    <div className="bg-white rounded-2xl p-6 shadow-md border border-gray-100 transform hover:scale-[1.02] transition-transform duration-200 flex flex-col justify-between">
                        <div className="flex justify-between items-start">
                            <div>
                                <p className="text-gray-500 font-medium text-sm">시스템 관리</p>
                                <div className="mt-3 flex items-baseline gap-2">
                                    <h3 className="text-4xl font-bold text-gray-800">{stats.total_users}</h3>
                                    <span className="text-gray-400 text-sm">명 (전체 회원)</span>
                                </div>
                            </div>
                            <div className="p-3 bg-gray-100 rounded-xl">
                                <Users className="text-gray-600 w-6 h-6" />
                            </div>
                        </div>
                        <div className="mt-4 space-y-2">
                            <button
                                onClick={() => router.push('/admin/users')}
                                className="w-full py-2 bg-indigo-50 text-indigo-600 rounded-lg text-sm font-semibold hover:bg-indigo-100 transition-colors flex items-center justify-center gap-2"
                            >
                                회원 관리 <ArrowRight size={14} />
                            </button>
                            <button
                                onClick={() => router.push('/admin/qr')}
                                className="w-full py-2 bg-gray-50 text-gray-600 rounded-lg text-sm font-semibold hover:bg-gray-100 transition-colors flex items-center justify-center gap-2"
                            >
                                입장 QR 코드 <ArrowRight size={14} />
                            </button>
                        </div>
                    </div>
                </div>

                {/* Content Grid */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

                    {/* Active Users Table */}
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden flex flex-col h-[400px]">
                        <div className="p-6 border-b border-gray-100 flex justify-between items-center bg-white sticky top-0">
                            <div className="flex items-center gap-2">
                                <span className="flex h-2.5 w-2.5 relative">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-500"></span>
                                </span>
                                <h3 className="font-bold text-gray-800">실시간 입장 현황</h3>
                            </div>
                            <span className="text-xs text-gray-400 bg-gray-50 px-2 py-1 rounded-full border border-gray-100">Live</span>
                        </div>

                        <div className="overflow-y-auto flex-1 p-0">
                            <table className="min-w-full divide-y divide-gray-50">
                                <thead className="bg-gray-50/50 sticky top-0">
                                    <tr>
                                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-400 uppercase">이름</th>
                                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-400 uppercase">시설</th>
                                        <th className="px-6 py-3 text-right text-xs font-semibold text-gray-400 uppercase">입장 시간</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-50">
                                    {currentUsers.length > 0 ? (
                                        currentUsers.map((user) => (
                                            <tr key={user.id} className="hover:bg-gray-50 transition-colors">
                                                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{user.name}</td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${user.type === 'Health' ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'
                                                        }`}>
                                                        {user.type === 'Health' ? '헬스장' : '스크린골프'}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400 text-right font-mono">
                                                    {new Date(user.enter_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                </td>
                                            </tr>
                                        ))
                                    ) : (
                                        <tr>
                                            <td colSpan={3} className="px-6 py-24 text-center text-gray-400 bg-gray-50/30">
                                                <div className="flex flex-col items-center justify-center gap-3">
                                                    <Clock className="w-8 h-8 text-gray-300" />
                                                    <span>현재 이용 중인 회원이 없습니다.</span>
                                                </div>
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Weekly Stats Chart */}
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 h-[400px] flex flex-col">
                        <div className="mb-6 flex justify-between items-center">
                            <h3 className="font-bold text-gray-800 flex items-center gap-2">
                                <CalendarClock className="w-5 h-5 text-gray-500" />
                                {period === 'month' ? '월간 이용 통계' : '주간 이용 통계'}
                            </h3>
                            <select
                                value={period}
                                onChange={(e) => setPeriod(e.target.value)}
                                className="text-xs border border-gray-200 rounded-lg px-2 py-1 text-gray-500 focus:outline-none focus:border-blue-500"
                            >
                                <option value="this_week">이번 주</option>
                                <option value="last_week">지난 주</option>
                                <option value="month">이번 달</option>
                            </select>
                        </div>

                        <div className="flex-1 w-full min-h-0">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                    data={chartData}
                                    margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                                    barSize={20}
                                >
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f3f4f6" />
                                    <XAxis
                                        dataKey="name"
                                        interval={0}
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#9ca3af', fontSize: 12 }}
                                        dy={10}
                                    />
                                    <YAxis
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#9ca3af', fontSize: 12 }}
                                    />
                                    <Tooltip
                                        cursor={{ fill: '#f9fafb' }}
                                        content={({ active, payload, label }) => {
                                            if (active && payload && payload.length) {
                                                const data = payload[0].payload;
                                                return (
                                                    <div className="bg-white p-4 rounded-xl shadow-lg border border-gray-100 ring-1 ring-black/5">
                                                        <p className="font-bold text-gray-900 mb-2">{data.name} ({data.date})</p>

                                                        {data.health > 0 && (
                                                            <div className="mb-2">
                                                                <p className="text-xs font-semibold text-blue-600 mb-1">헬스장 사용 ({data.health}명)</p>
                                                                <p className="text-xs text-gray-500 leading-relaxed max-w-[150px]">{data.health_users.join(', ') || '-'}</p>
                                                            </div>
                                                        )}

                                                        {data.golf > 0 && (
                                                            <div>
                                                                <p className="text-xs font-semibold text-emerald-600 mb-1">스크린골프 사용 ({data.golf}명)</p>
                                                                <p className="text-xs text-gray-500 leading-relaxed max-w-[150px]">{data.golf_users.join(', ') || '-'}</p>
                                                            </div>
                                                        )}

                                                        {data.health === 0 && data.golf === 0 && (
                                                            <p className="text-xs text-gray-400">이용 내역 없음</p>
                                                        )}
                                                    </div>
                                                );
                                            }
                                            return null;
                                        }}
                                    />
                                    <Legend iconType="circle" wrapperStyle={{ paddingTop: '20px' }} />
                                    <Bar dataKey="health" name="헬스장" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                                    <Bar dataKey="golf" name="스크린골프" fill="#10b981" radius={[4, 4, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
}
