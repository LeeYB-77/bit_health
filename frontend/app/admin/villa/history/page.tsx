'use client';
// 비트별장 예약 이력·통계 화면. 기간·별장·상태로 과거 예약을 조회하고 운영 통계를 보여준다.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { API_URL, getVillas, Villa } from '@/lib/api';
import { ArrowLeft, Download, Loader2 } from 'lucide-react';
import {
    Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
    ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

interface HistoryRow {
    id: number;
    facility_name: string | null;
    user_name: string;
    user_dept: string | null;
    start_date: string;
    end_date: string;
    nights: number;
    status: string;
    status_label: string;
    booking_type: string | null;
    booking_type_label: string | null;
    participant_count: number;
    adult_count: number | null;
    child_count: number | null;
    cancel_reason: string | null;
    created_at: string | null;
}

interface HistoryResponse {
    from_month: string;
    to_month: string;
    summary: {
        confirmed_count: number;
        total_nights: number;
        cancel_rate: number;
        avg_participants: number;
    };
    monthly: { month: string; count: number; nights: number }[];
    by_facility: { facility: string; count: number; nights: number }[];
    by_status: { label: string; count: number }[];
    by_booking_type: { type: string; label: string; count: number }[];
    reservations: HistoryRow[];
}

const authHeaders = (): HeadersInit => ({
    Authorization: `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('access_token') : ''}`,
});

const STATUS_CLS: Record<string, string> = {
    확정: 'bg-blue-100 text-blue-700',
    취소: 'bg-rose-100 text-rose-700',
    미선정: 'bg-gray-100 text-gray-500',
    신청중: 'bg-amber-100 text-amber-700',
};

const STATUS_COLORS: Record<string, string> = {
    확정: '#3b82f6',
    취소: '#f43f5e',
    미선정: '#9ca3af',
    신청중: '#f59e0b',
};
const TYPE_COLORS = ['#6366f1', '#14b8a6'];

const thisYear = new Date().getFullYear();

export default function VillaHistoryPage() {
    const router = useRouter();
    const [villas, setVillas] = useState<Villa[]>([]);
    const [fromMonth, setFromMonth] = useState(`${thisYear}-01`);
    const [toMonth, setToMonth] = useState(`${thisYear}-12`);
    const [facilityId, setFacilityId] = useState<number | ''>('');
    const [status, setStatus] = useState('');

    const [data, setData] = useState<HistoryResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [exporting, setExporting] = useState(false);
    const [message, setMessage] = useState<string | null>(null);

    const queryString = useMemo(() => {
        const p = new URLSearchParams();
        p.set('from_month', fromMonth);
        p.set('to_month', toMonth);
        if (facilityId !== '') p.set('facility_id', String(facilityId));
        if (status) p.set('status', status);
        return p.toString();
    }, [fromMonth, toMonth, facilityId, status]);

    const load = useCallback(async () => {
        setLoading(true);
        setMessage(null);
        try {
            const res = await fetch(`${API_URL}/api/villa/admin/history?${queryString}`, { headers: authHeaders() });
            const body = await res.json();
            if (!res.ok) throw new Error(body.detail || '조회에 실패했습니다.');
            setData(body);
        } catch (e) {
            setMessage(e instanceof Error ? e.message : '조회에 실패했습니다.');
        } finally {
            setLoading(false);
        }
    }, [queryString]);

    useEffect(() => {
        if (typeof window !== 'undefined' && !localStorage.getItem('access_token')) {
            router.replace('/login?redirect=/admin/villa/history');
            return;
        }
        getVillas().then(setVillas).catch(() => {});
    }, [router]);

    useEffect(() => { load(); }, [load]);

    const exportExcel = async () => {
        setExporting(true);
        setMessage(null);
        try {
            const res = await fetch(`${API_URL}/api/villa/admin/history/export?${queryString}`, { headers: authHeaders() });
            if (!res.ok) throw new Error('내보내기에 실패했습니다.');
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `villa_history_${fromMonth}_${toMonth}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            setMessage(e instanceof Error ? e.message : '내보내기에 실패했습니다.');
        } finally {
            setExporting(false);
        }
    };

    const summaryCards = data ? [
        { label: '확정 건수', value: `${data.summary.confirmed_count}건` },
        { label: '총 숙박', value: `${data.summary.total_nights}박` },
        { label: '취소율', value: `${data.summary.cancel_rate}%` },
        { label: '평균 인원', value: `${data.summary.avg_participants}명` },
    ] : [];

    const selectCls = 'rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1.5 text-sm outline-none focus:ring-2 focus:ring-blue-500';

    return (
        <div className="space-y-6 px-4 sm:px-0">
            <div className="flex items-center gap-3">
                <button onClick={() => router.push('/admin/villa')} className="p-2 rounded-full hover:bg-gray-100 text-gray-500">
                    <ArrowLeft size={20} />
                </button>
                <h2 className="text-xl font-bold text-gray-900">비트별장 예약 이력·통계</h2>
            </div>

            {/* 필터 */}
            <section className="rounded-2xl bg-white shadow-sm border border-gray-100 p-4 flex flex-wrap items-center gap-2">
                <input type="month" value={fromMonth} onChange={e => setFromMonth(e.target.value)} className={selectCls} />
                <span className="text-gray-400">~</span>
                <input type="month" value={toMonth} onChange={e => setToMonth(e.target.value)} className={selectCls} />
                <select value={facilityId} onChange={e => setFacilityId(e.target.value === '' ? '' : Number(e.target.value))} className={selectCls}>
                    <option value="">전체 별장</option>
                    {villas.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
                <select value={status} onChange={e => setStatus(e.target.value)} className={selectCls}>
                    <option value="">전체 상태</option>
                    <option value="confirmed">확정</option>
                    <option value="canceled">취소</option>
                    <option value="rejected">미선정</option>
                    <option value="applied">신청중</option>
                </select>
                <button
                    onClick={exportExcel}
                    disabled={exporting || !data}
                    className="ml-auto px-3 py-1.5 text-sm font-bold text-emerald-700 border border-emerald-200 rounded-lg hover:bg-emerald-50 disabled:opacity-50 flex items-center gap-1.5"
                >
                    {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                    엑셀 내보내기
                </button>
            </section>

            {message && (
                <div className="rounded-xl bg-rose-50 border border-rose-100 p-3 text-sm text-rose-700">{message}</div>
            )}

            {loading ? (
                <div className="p-10 text-center text-gray-400">불러오는 중...</div>
            ) : data && (
                <>
                    {/* 요약 카드 */}
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                        {summaryCards.map(c => (
                            <div key={c.label} className="rounded-2xl bg-white shadow-sm border border-gray-100 p-4">
                                <p className="text-xs text-gray-400">{c.label}</p>
                                <p className="text-2xl font-bold text-gray-900 mt-1">{c.value}</p>
                            </div>
                        ))}
                    </div>

                    {/* 월별 추이 */}
                    <section className="rounded-2xl bg-white shadow-sm border border-gray-100 p-4">
                        <h3 className="text-sm font-bold text-gray-800 mb-3">월별 이용 추이</h3>
                        <ResponsiveContainer width="100%" height={240}>
                            <BarChart data={data.monthly} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                                <XAxis dataKey="month" tick={{ fontSize: 11 }} tickFormatter={m => m.slice(5)} />
                                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                                <Tooltip />
                                <Legend wrapperStyle={{ fontSize: 12 }} />
                                <Bar dataKey="count" name="건수" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                                <Bar dataKey="nights" name="박수" fill="#93c5fd" radius={[3, 3, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </section>

                    <div className="grid md:grid-cols-3 gap-4">
                        {/* 별장별 */}
                        <section className="rounded-2xl bg-white shadow-sm border border-gray-100 p-4">
                            <h3 className="text-sm font-bold text-gray-800 mb-3">별장별 이용</h3>
                            <ResponsiveContainer width="100%" height={200}>
                                <BarChart data={data.by_facility} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                                    <XAxis dataKey="facility" tick={{ fontSize: 11 }} />
                                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                                    <Tooltip />
                                    <Bar dataKey="count" name="건수" fill="#6366f1" radius={[3, 3, 0, 0]} />
                                </BarChart>
                            </ResponsiveContainer>
                        </section>

                        {/* 상태 분포 */}
                        <section className="rounded-2xl bg-white shadow-sm border border-gray-100 p-4">
                            <h3 className="text-sm font-bold text-gray-800 mb-3">상태 분포</h3>
                            <ResponsiveContainer width="100%" height={180}>
                                <PieChart>
                                    <Pie data={data.by_status} dataKey="count" nameKey="label" cx="50%" cy="50%" outerRadius={65}>
                                        {data.by_status.map(s => <Cell key={s.label} fill={STATUS_COLORS[s.label] ?? '#cbd5e1'} />)}
                                    </Pie>
                                    <Tooltip />
                                </PieChart>
                            </ResponsiveContainer>
                            <div className="flex flex-wrap justify-center gap-x-3 gap-y-1 mt-2 text-xs text-gray-600">
                                {data.by_status.map(s => (
                                    <span key={s.label} className="flex items-center gap-1">
                                        <span className="w-2 h-2 rounded-full" style={{ background: STATUS_COLORS[s.label] ?? '#cbd5e1' }} />
                                        {s.label} {s.count}
                                    </span>
                                ))}
                            </div>
                        </section>

                        {/* 신청 유형 */}
                        <section className="rounded-2xl bg-white shadow-sm border border-gray-100 p-4">
                            <h3 className="text-sm font-bold text-gray-800 mb-3">신청 유형</h3>
                            <ResponsiveContainer width="100%" height={180}>
                                <PieChart>
                                    <Pie data={data.by_booking_type} dataKey="count" nameKey="label" cx="50%" cy="50%" outerRadius={65}>
                                        {data.by_booking_type.map((b, i) => <Cell key={b.type} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />)}
                                    </Pie>
                                    <Tooltip />
                                </PieChart>
                            </ResponsiveContainer>
                            <div className="flex flex-wrap justify-center gap-x-3 gap-y-1 mt-2 text-xs text-gray-600">
                                {data.by_booking_type.map((b, i) => (
                                    <span key={b.type} className="flex items-center gap-1">
                                        <span className="w-2 h-2 rounded-full" style={{ background: TYPE_COLORS[i % TYPE_COLORS.length] }} />
                                        {b.label} {b.count}
                                    </span>
                                ))}
                            </div>
                        </section>
                    </div>

                    {/* 이력 테이블 */}
                    <section className="rounded-2xl bg-white shadow-sm border border-gray-100 overflow-hidden">
                        <div className="px-5 py-3 border-b border-gray-100 flex items-center">
                            <h3 className="text-sm font-bold text-gray-800">예약 이력</h3>
                            <span className="ml-2 text-xs text-gray-400">{data.reservations.length}건</span>
                        </div>
                        {data.reservations.length === 0 ? (
                            <div className="p-10 text-center text-gray-400">해당 조건의 예약이 없습니다.</div>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
                                            <th className="px-4 py-2 font-medium">이용자</th>
                                            <th className="px-4 py-2 font-medium">별장</th>
                                            <th className="px-4 py-2 font-medium">기간</th>
                                            <th className="px-4 py-2 font-medium">상태</th>
                                            <th className="px-4 py-2 font-medium">인원</th>
                                            <th className="px-4 py-2 font-medium">유형</th>
                                            <th className="px-4 py-2 font-medium">취소사유</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {data.reservations.map(r => (
                                            <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50">
                                                <td className="px-4 py-2.5">
                                                    <span className="font-medium text-gray-800">{r.user_name}</span>
                                                    {r.user_dept && <span className="text-gray-400 text-xs ml-1">{r.user_dept}</span>}
                                                </td>
                                                <td className="px-4 py-2.5 text-gray-600">{r.facility_name}</td>
                                                <td className="px-4 py-2.5 text-gray-600 whitespace-nowrap">
                                                    {r.start_date} ~ {r.end_date}
                                                    <span className="text-gray-400 ml-1">({r.nights}박)</span>
                                                </td>
                                                <td className="px-4 py-2.5">
                                                    <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold ${STATUS_CLS[r.status_label] ?? 'bg-gray-100 text-gray-500'}`}>
                                                        {r.status_label}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-2.5 text-gray-600">
                                                    {r.participant_count}명
                                                    {(r.adult_count != null || r.child_count != null) && (
                                                        <span className="text-gray-400 text-xs ml-1">
                                                            (성인 {r.adult_count ?? '-'}·아동 {r.child_count ?? '-'})
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-2.5 text-gray-500 text-xs">{r.booking_type_label}</td>
                                                <td className="px-4 py-2.5 text-gray-500 text-xs max-w-[180px] truncate">{r.cancel_reason || '-'}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </section>
                </>
            )}
        </div>
    );
}
