'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { API_URL, GolfSettings } from '@/lib/api';
import {
    Calendar,
    Clock,
    Settings,
    ArrowLeft,
    CheckCircle,
    XCircle,
    Trash2,
    Plus
} from 'lucide-react';

interface Reservation {
    id: number;
    start_time: string;
    end_time: string;
    participant_count: number;
    companions: string;
    status: string;
    user_name: string;
    user_dept: string;
}

export default function AdminGolfPage() {
    const router = useRouter();
    const [activeTab, setActiveTab] = useState<'reservations' | 'settings'>('reservations');
    const [date, setDate] = useState<string>('');
    const [reservations, setReservations] = useState<Reservation[]>([]);

    // Settings State
    const [settings, setSettings] = useState<GolfSettings>({
        weekday_slots: [{ start: '10:00', end: '12:00' }, { start: '14:00', end: '16:00' }, { start: '19:00', end: '21:00' }],
        weekend_start: 9,
        weekend_end: 18
    });

    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

    useEffect(() => {
        const today = new Date().toISOString().split('T')[0];
        setDate(today);
        fetchSettings();
    }, []);

    useEffect(() => {
        if (activeTab === 'reservations' && date) {
            fetchReservations(date);
        }
    }, [activeTab, date]);

    const fetchReservations = async (selectedDate: string) => {
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await fetch(`${API_URL}/api/golf/admin/reservations?date=${selectedDate}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Failed to fetch reservations');
            setReservations(await res.json());
        } catch (err: any) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const fetchSettings = async () => {
        try {
            const token = localStorage.getItem('access_token');
            const res = await fetch(`${API_URL}/api/golf/settings`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                // Migration check: ensure weekday_slots is object array
                if (data.weekday_slots && data.weekday_slots.length > 0 && typeof data.weekday_slots[0] === 'string') {
                    // Convert old string format to object
                    data.weekday_slots = data.weekday_slots.map((s: string) => ({ start: s, end: '00:00' }));
                }
                setSettings({
                    weekday_slots: data.weekday_slots || [],
                    weekend_start: data.weekend_start ?? 9,
                    weekend_end: data.weekend_end ?? 18
                });
            }
        } catch (err) {
            console.error(err);
        }
    };

    const handleUpdateSettings = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        try {
            const token = localStorage.getItem('access_token');
            const res = await fetch(`${API_URL}/api/golf/settings`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            });

            if (!res.ok) throw new Error('Failed to update settings');
            setMessage({ type: 'success', text: '설정이 저장되었습니다.' });
        } catch (err: any) {
            setMessage({ type: 'error', text: err.message });
        } finally {
            setLoading(false);
        }
    };

    const addSlot = () => {
        setSettings({
            ...settings,
            weekday_slots: [...(settings.weekday_slots || []), { start: '00:00', end: '00:00' }]
        });
    };

    const removeSlot = (index: number) => {
        const newSlots = [...(settings.weekday_slots || [])];
        newSlots.splice(index, 1);
        setSettings({ ...settings, weekday_slots: newSlots });
    };

    const updateSlot = (index: number, field: 'start' | 'end', value: string) => {
        const newSlots = [...(settings.weekday_slots || [])];
        newSlots[index] = { ...newSlots[index], [field]: value };
        setSettings({ ...settings, weekday_slots: newSlots });
    };

    const handleCancelReservation = async (id: number) => {
        if (!confirm('예약을 취소하시겠습니까?')) return;
        try {
            const token = localStorage.getItem('access_token');
            const res = await fetch(`${API_URL}/api/golf/cancel/${id}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!res.ok) throw new Error('Cancellation failed');
            fetchReservations(date);
        } catch (err: any) {
            alert(err.message);
        }
    };

    return (
        <div className="min-h-screen bg-gray-50 font-sans text-gray-900">
            {/* Header */}
            <div className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-10">
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => router.push('/admin')}
                            className="p-2 rounded-full hover:bg-gray-100 transition-colors text-gray-500"
                        >
                            <ArrowLeft size={20} />
                        </button>
                        <h1 className="text-xl font-bold text-gray-800">스크린골프 관리</h1>
                    </div>
                </div>
            </div>

            <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

                {/* Navigation Tabs */}
                <div className="flex space-x-1 rounded-xl bg-gray-200 p-1 mb-8 w-fit">
                    <button
                        onClick={() => setActiveTab('reservations')}
                        className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all ${activeTab === 'reservations' ? 'bg-white text-blue-700 shadow' : 'text-gray-500 hover:text-gray-700'
                            }`}
                    >
                        <Calendar size={16} /> 예약 현황
                    </button>
                    <button
                        onClick={() => setActiveTab('settings')}
                        className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all ${activeTab === 'settings' ? 'bg-white text-blue-700 shadow' : 'text-gray-500 hover:text-gray-700'
                            }`}
                    >
                        <Settings size={16} /> 운영 설정
                    </button>
                </div>

                {message && (
                    <div className={`mb-6 p-4 rounded-lg flex items-center gap-3 shadow-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
                        }`}>
                        {message.type === 'success' ? <CheckCircle size={20} /> : <XCircle size={20} />}
                        <p className="text-sm font-medium">{message.text}</p>
                        <button onClick={() => setMessage(null)} className="ml-auto text-sm hover:underline">닫기</button>
                    </div>
                )}

                {/* Reservations View */}
                {activeTab === 'reservations' && (
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                        <div className="mb-6">
                            <label className="block text-sm font-medium text-gray-700 mb-2">날짜 선택</label>
                            <input
                                type="date"
                                value={date}
                                onChange={(e) => setDate(e.target.value)}
                                className="w-full max-w-xs rounded-lg border border-gray-300 p-2 text-sm"
                            />
                        </div>

                        <div className="space-y-4">
                            <h3 className="font-bold text-gray-800 border-b pb-2">예약 목록 ({reservations.length})</h3>
                            {loading ? (
                                <div className="text-center py-8 text-gray-400">Loading...</div>
                            ) : reservations.length > 0 ? (
                                <ul className="divide-y divide-gray-100">
                                    {reservations.map(res => (
                                        <li key={res.id} className="py-4 flex justify-between items-center group hover:bg-gray-50 rounded-lg px-2 transition-colors">
                                            <div>
                                                <div className="flex items-center gap-3 mb-1">
                                                    <span className="font-mono font-bold text-lg text-blue-600">
                                                        {new Date(res.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} ~ {new Date(res.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                    </span>
                                                    <span className={`text-xs px-2 py-0.5 rounded-full ${res.status === 'reserved' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                                                        }`}>
                                                        {res.status === 'reserved' ? '예약중' : '취소됨'}
                                                    </span>
                                                </div>
                                                <p className="text-sm text-gray-900 font-medium">
                                                    {res.user_name} <span className="text-gray-500 font-normal">({res.user_dept || '부서미기입'})</span>
                                                </p>
                                                <p className="text-xs text-gray-500 mt-0.5">
                                                    인원: {res.participant_count}명 {res.companions && `(동반: ${res.companions})`}
                                                </p>
                                            </div>
                                            {res.status === 'reserved' && (
                                                <button
                                                    onClick={() => handleCancelReservation(res.id)}
                                                    className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-full transition-all"
                                                    title="예약 취소"
                                                >
                                                    <Trash2 size={18} />
                                                </button>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <div className="text-center py-12 text-gray-400 bg-gray-50 rounded-xl">
                                    예약 내역이 없습니다.
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Settings View */}
                {activeTab === 'settings' && (
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8 max-w-lg mx-auto">
                        <h2 className="text-lg font-bold text-gray-900 mb-6 flex items-center gap-2">
                            <Clock className="text-blue-600" /> 운영 시간 설정
                        </h2>

                        <form onSubmit={handleUpdateSettings} className="space-y-8">
                            {/* Weekday - Specific Slots */}
                            <div className="bg-gray-50 p-6 rounded-xl border border-gray-200">
                                <h3 className="text-sm font-bold text-gray-700 mb-4 flex items-center justify-between">
                                    <span>평일 (월~금) 예약 타임</span>
                                    <span className="text-xs font-normal text-gray-500">지정된 시간대만 에약 가능</span>
                                </h3>

                                <div className="space-y-3">
                                    {settings.weekday_slots?.map((slot, idx) => (
                                        <div key={idx} className="flex items-center gap-2">
                                            <div className="flex-1 flex items-center gap-2 bg-white p-2 rounded-xl border border-gray-200">
                                                <input
                                                    type="time"
                                                    value={slot.start}
                                                    onChange={(e) => updateSlot(idx, 'start', e.target.value)}
                                                    className="bg-transparent text-center font-mono font-bold outline-none w-24 text-gray-700"
                                                />
                                                <span className="text-gray-400">~</span>
                                                <input
                                                    type="time"
                                                    value={slot.end}
                                                    onChange={(e) => updateSlot(idx, 'end', e.target.value)}
                                                    className="bg-transparent text-center font-mono font-bold outline-none w-24 text-gray-700"
                                                />
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => removeSlot(idx)}
                                                className="p-3 text-red-500 hover:bg-red-50 rounded-xl transition-colors"
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                        </div>
                                    ))}
                                    <button
                                        type="button"
                                        onClick={addSlot}
                                        className="w-full py-3 border border-dashed border-gray-300 rounded-xl text-gray-500 hover:bg-gray-100 hover:border-blue-300 hover:text-blue-500 transition-colors flex items-center justify-center gap-2"
                                    >
                                        <Plus size={18} /> 슬롯 추가
                                    </button>
                                </div>
                            </div>

                            {/* Weekend - Range */}
                            <div className="bg-gray-50 p-6 rounded-xl border border-gray-200">
                                <h3 className="text-sm font-bold text-gray-700 mb-4 block">주말/공휴일 운영 시간</h3>
                                <div className="flex items-center justify-between gap-4">
                                    <div className="flex-1">
                                        <label className="block text-xs text-gray-500 mb-1">시작 시간</label>
                                        <div className="relative">
                                            <select
                                                value={settings.weekend_start}
                                                onChange={(e) => setSettings({ ...settings, weekend_start: Number(e.target.value) })}
                                                className="w-full appearance-none bg-white border border-gray-300 rounded-lg py-2 px-4 pr-8 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                            >
                                                {Array.from({ length: 24 }, (_, i) => (
                                                    <option key={i} value={i}>{String(i).padStart(2, '0')}:00</option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>
                                    <span className="text-gray-400 mt-4">~</span>
                                    <div className="flex-1">
                                        <label className="block text-xs text-gray-500 mb-1">종료 시간</label>
                                        <div className="relative">
                                            <select
                                                value={settings.weekend_end}
                                                onChange={(e) => setSettings({ ...settings, weekend_end: Number(e.target.value) })}
                                                className="w-full appearance-none bg-white border border-gray-300 rounded-lg py-2 px-4 pr-8 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                            >
                                                {Array.from({ length: 24 }, (_, i) => (
                                                    <option key={i} value={i}>{String(i).padStart(2, '0')}:00</option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                <p className="text-xs text-orange-500 mt-2">
                                    * 법정 공휴일은 자동으로 주말 운영 시간이 적용됩니다.
                                </p>
                            </div>

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
                            >
                                {loading ? '저장 중...' : '설정 저장'}
                            </button>
                        </form>
                    </div>
                )}
            </div>
        </div>
    );
}
