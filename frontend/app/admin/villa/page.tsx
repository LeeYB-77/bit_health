'use client';
// 비트별장 관리자 화면. 중복 경합 신청을 나란히 비교해 확정하고, 취소 요청을 승인·반려한다.

import { useCallback, useEffect, useState } from 'react';
import { API_URL } from '@/lib/api';
import { AlertTriangle, Calendar, Check, Loader2, Send, Users, X } from 'lucide-react';

interface Application {
    id: number;
    facility_id: number;
    facility_name: string | null;
    user_id: number;
    user_name: string;
    user_dept: string | null;
    start_date: string;
    end_date: string;
    nights: number;
    checkin_time: string | null;
    checkout_time: string | null;
    participant_count: number;
    status: string;
    created_at: string;
    usage_count: number;
}

interface Group {
    facility_id: number;
    facility_name: string | null;
    start_date: string;
    end_date: string;
    count: number;
    contested: boolean;
    applications: Application[];
}

interface RoundInfo {
    id: number;
    status: string;
    apply_end: string;
    notify_date: string;
}

interface ApplicationsResponse {
    year: number;
    month: number;
    pending_total: number;
    contested_groups: number;
    groups: Group[];
    confirmed: Application[];
    round: RoundInfo | null;
    unnotified_count: number;
}

interface CancelRequest {
    id: number;
    facility_name: string | null;
    user_name: string;
    user_dept: string | null;
    start_date: string;
    end_date: string;
    nights: number;
    participant_count: number;
    cancel_requested_at: string | null;
    cancel_reason: string | null;
}

const authHeaders = (): HeadersInit => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('access_token') : ''}`,
});

async function call(path: string, method: 'GET' | 'POST' = 'GET') {
    const res = await fetch(`${API_URL}${path}`, { method, headers: authHeaders() });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || '요청에 실패했습니다.');
    return body;
}

const shiftMonth = (year: number, month: number, delta: number) => {
    const i = year * 12 + (month - 1) + delta;
    return { year: Math.floor(i / 12), month: (i % 12) + 1 };
};

export default function AdminVillaPage() {
    const [data, setData] = useState<ApplicationsResponse | null>(null);
    const [cancels, setCancels] = useState<CancelRequest[]>([]);
    const [view, setView] = useState<{ year: number; month: number } | null>(null);
    const [loading, setLoading] = useState(true);
    const [busyId, setBusyId] = useState<number | null>(null);
    const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

    const load = useCallback(async (target?: { year: number; month: number }) => {
        try {
            const query = target ? `?year=${target.year}&month=${target.month}` : '';
            const [apps, cancelList] = await Promise.all([
                call(`/api/villa/admin/applications${query}`),
                call('/api/villa/admin/cancel-requests'),
            ]);
            setData(apps);
            setCancels(cancelList);
            setView({ year: apps.year, month: apps.month });
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '불러오지 못했습니다.' });
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const act = async (id: number, path: string, okText: string) => {
        setBusyId(id);
        setMessage(null);
        try {
            const body = await call(path, 'POST');
            setMessage({ type: 'ok', text: body.message || okText });
            await load(view ?? undefined);
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '처리에 실패했습니다.' });
        } finally {
            setBusyId(null);
        }
    };

    if (loading) {
        return <div className="p-8 text-center text-gray-500">불러오는 중...</div>;
    }

    return (
        <div className="space-y-6 px-4 sm:px-0">
            <div className="flex items-center justify-between flex-wrap gap-3">
                <h2 className="text-xl font-bold text-gray-900">비트별장 예약 관리</h2>
                {view && (
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => load(shiftMonth(view.year, view.month, -1))}
                            className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
                        >
                            이전 달
                        </button>
                        <span className="font-bold text-gray-700 min-w-28 text-center">
                            {view.year}년 {view.month}월
                        </span>
                        <button
                            onClick={() => load(shiftMonth(view.year, view.month, 1))}
                            className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
                        >
                            다음 달
                        </button>
                    </div>
                )}
            </div>

            {message && (
                <div className={`rounded-xl p-3 text-sm flex items-start gap-2 ${
                    message.type === 'ok'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-100'
                        : 'bg-rose-50 text-rose-700 border border-rose-100'
                }`}>
                    <span className="flex-1">{message.text}</span>
                    <button onClick={() => setMessage(null)}><X size={16} /></button>
                </div>
            )}

            {/* 취소 요청 — 방치되면 해당 기간이 계속 묶이므로 최상단에 둔다 */}
            {cancels.length > 0 && (
                <section className="rounded-2xl bg-white shadow-sm border-2 border-orange-200 overflow-hidden">
                    <div className="bg-orange-50 px-5 py-3 flex items-center gap-2 border-b border-orange-100">
                        <AlertTriangle size={18} className="text-orange-600" />
                        <h3 className="font-bold text-orange-800">취소 요청 {cancels.length}건</h3>
                        <span className="text-xs text-orange-600 ml-auto">
                            승인 전까지 해당 기간이 계속 점유됩니다
                        </span>
                    </div>
                    <ul className="divide-y divide-gray-100">
                        {cancels.map(c => (
                            <li key={c.id} className="p-4 flex items-start justify-between gap-4 flex-wrap">
                                <div className="min-w-0">
                                    <p className="font-bold text-gray-800">
                                        {c.user_name}
                                        {c.user_dept && <span className="text-gray-400 font-normal"> · {c.user_dept}</span>}
                                    </p>
                                    <p className="text-sm text-gray-600 mt-0.5">
                                        {c.facility_name} · {c.start_date} ~ {c.end_date} ({c.nights}박) · {c.participant_count}명
                                    </p>
                                    <p className="text-sm text-gray-500 mt-1">
                                        사유: {c.cancel_reason || <span className="text-gray-400">미입력</span>}
                                    </p>
                                </div>
                                <div className="flex gap-2 shrink-0">
                                    <button
                                        onClick={() => act(c.id, `/api/villa/admin/cancel-approve/${c.id}`, '승인했습니다.')}
                                        disabled={busyId === c.id}
                                        className="px-3 py-1.5 text-sm font-bold text-white bg-rose-600 rounded-lg hover:bg-rose-700 disabled:opacity-50"
                                    >
                                        {busyId === c.id ? <Loader2 size={14} className="animate-spin" /> : '취소 승인'}
                                    </button>
                                    <button
                                        onClick={() => act(c.id, `/api/villa/admin/cancel-reject/${c.id}`, '반려했습니다.')}
                                        disabled={busyId === c.id}
                                        className="px-3 py-1.5 text-sm font-bold text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
                                    >
                                        반려
                                    </button>
                                </div>
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            {/* 요약 */}
            {data && (
                <div className="grid grid-cols-3 gap-3">
                    {[
                        { label: '대기 신청', value: data.pending_total, cls: 'text-amber-600' },
                        { label: '경합 그룹', value: data.contested_groups, cls: 'text-rose-600' },
                        { label: '확정', value: data.confirmed.length, cls: 'text-blue-600' },
                    ].map(s => (
                        <div key={s.label} className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <p className="text-xs text-gray-400">{s.label}</p>
                            <p className={`text-2xl font-bold mt-1 ${s.cls}`}>{s.value}</p>
                        </div>
                    ))}
                </div>
            )}

            {/* 확정 결과 통보 */}
            {data?.round && (
                <section className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100 flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <h3 className="font-bold text-gray-800 flex items-center gap-2">
                            <Send size={16} className="text-blue-600" /> 확정 결과 통보
                        </h3>
                        <p className="text-sm text-gray-500 mt-1">
                            접수 마감 {data.round.apply_end} · 통보 예정일 {data.round.notify_date}
                        </p>
                        <p className="text-xs text-gray-400 mt-1">
                            {data.pending_total > 0
                                ? `대기 중인 신청 ${data.pending_total}건을 모두 확정해야 통보할 수 있습니다.`
                                : data.unnotified_count > 0
                                    ? `미통보 ${data.unnotified_count}건에 Slack·메일로 결과를 보냅니다.`
                                    : '통보할 새 건이 없습니다.'}
                        </p>
                    </div>
                    <button
                        onClick={() => act(-1, `/api/villa/admin/notify/${data.round!.id}`, '통보했습니다.')}
                        disabled={busyId === -1 || data.pending_total > 0 || data.unnotified_count === 0}
                        className="px-4 py-2 text-sm font-bold text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-1.5 shrink-0"
                    >
                        {busyId === -1
                            ? <Loader2 size={14} className="animate-spin" />
                            : <><Send size={14} /> 결과 통보</>}
                    </button>
                </section>
            )}

            {/* 신청 그룹 */}
            <section className="space-y-4">
                <h3 className="font-bold text-gray-800 flex items-center gap-2">
                    <Users size={18} className="text-blue-600" /> 신청 현황
                </h3>

                {!data || data.groups.length === 0 ? (
                    <div className="rounded-2xl bg-white p-10 text-center text-gray-400 border border-gray-100 border-dashed">
                        대기 중인 신청이 없습니다.
                    </div>
                ) : data.groups.map(group => (
                    <div
                        key={`${group.facility_id}-${group.start_date}-${group.end_date}`}
                        className={`rounded-2xl bg-white shadow-sm overflow-hidden border ${
                            group.contested ? 'border-amber-300' : 'border-gray-100'
                        }`}
                    >
                        <div className={`px-5 py-3 flex items-center gap-2 border-b ${
                            group.contested ? 'bg-amber-50 border-amber-100' : 'bg-gray-50 border-gray-100'
                        }`}>
                            <Calendar size={16} className={group.contested ? 'text-amber-600' : 'text-gray-400'} />
                            <span className="font-bold text-gray-800">
                                {group.facility_name} · {group.start_date} ~ {group.end_date}
                            </span>
                            {group.contested && (
                                <span className="text-xs font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                                    {group.count}팀 경합
                                </span>
                            )}
                        </div>

                        <ul className="divide-y divide-gray-100">
                            {group.applications.map((a, idx) => (
                                <li key={a.id} className="p-4 flex items-start justify-between gap-4 flex-wrap">
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            {group.contested && (
                                                <span className="text-xs font-bold text-gray-400">#{idx + 1}</span>
                                            )}
                                            <span className="font-bold text-gray-800">{a.user_name}</span>
                                            {a.user_dept && <span className="text-sm text-gray-400">{a.user_dept}</span>}
                                            <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${
                                                a.usage_count === 0
                                                    ? 'bg-emerald-100 text-emerald-700'
                                                    : 'bg-gray-100 text-gray-600'
                                            }`}>
                                                최근 1년 {a.usage_count}회 이용
                                            </span>
                                        </div>
                                        <p className="text-sm text-gray-600 mt-1">
                                            {a.start_date} ~ {a.end_date} ({a.nights}박) · {a.participant_count}명
                                            · {a.checkin_time} 입실 / {a.checkout_time} 퇴실
                                        </p>
                                        <p className="text-xs text-gray-400 mt-0.5">
                                            신청 {a.created_at ? new Date(a.created_at).toLocaleString('ko-KR') : '-'}
                                        </p>
                                    </div>

                                    <button
                                        onClick={() => act(a.id, `/api/villa/admin/confirm/${a.id}`, '확정했습니다.')}
                                        disabled={busyId === a.id}
                                        className="px-4 py-2 text-sm font-bold text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1.5 shrink-0"
                                    >
                                        {busyId === a.id
                                            ? <Loader2 size={14} className="animate-spin" />
                                            : <><Check size={14} /> 확정</>}
                                    </button>
                                </li>
                            ))}
                        </ul>

                        {group.contested && (
                            <p className="px-5 py-2.5 text-xs text-gray-500 bg-gray-50 border-t border-gray-100">
                                확정하면 이 기간과 겹치는 다른 신청은 자동으로 미선정 처리됩니다.
                            </p>
                        )}
                    </div>
                ))}
            </section>

            {/* 확정 목록 */}
            {data && data.confirmed.length > 0 && (
                <section className="rounded-2xl bg-white shadow-sm border border-gray-100 overflow-hidden">
                    <div className="bg-blue-50 px-5 py-3 border-b border-blue-100">
                        <h3 className="font-bold text-blue-800">확정된 예약 {data.confirmed.length}건</h3>
                    </div>
                    <ul className="divide-y divide-gray-100">
                        {data.confirmed.map(c => (
                            <li key={c.id} className="p-4 flex items-center justify-between gap-4 flex-wrap">
                                <div>
                                    <p className="font-bold text-gray-800">
                                        {c.user_name}
                                        {c.user_dept && <span className="text-gray-400 font-normal"> · {c.user_dept}</span>}
                                    </p>
                                    <p className="text-sm text-gray-600 mt-0.5">
                                        {c.facility_name} · {c.start_date} ~ {c.end_date} ({c.nights}박) · {c.participant_count}명
                                    </p>
                                </div>
                                <span className={`text-xs px-2.5 py-1 rounded-full font-bold ${
                                    c.status === 'cancel_requested'
                                        ? 'bg-orange-100 text-orange-700'
                                        : 'bg-blue-100 text-blue-700'
                                }`}>
                                    {c.status === 'cancel_requested' ? '취소 요청중' : '확정'}
                                </span>
                            </li>
                        ))}
                    </ul>
                </section>
            )}
        </div>
    );
}
