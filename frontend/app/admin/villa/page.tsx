'use client';
// 비트별장 관리자 화면. 중복 경합 신청을 나란히 비교해 확정하고, 취소 요청을 승인·반려한다.
// 예약 현황은 이번달·선착순예약월·예약신청대상월 3개월 달력으로 한눈에 보여준다.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { API_URL, getVillas, Villa } from '@/lib/api';
import { AlertTriangle, ArrowLeft, Calendar, Check, Loader2, Send, Users, X } from 'lucide-react';

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
    checkin_time_forced: boolean;
    checkout_time_forced: boolean;
    participant_count: number;
    status: string;
    booking_type: string;
    created_at: string;
    usage_count: number;
    vehicle_count: number | null;
    vehicle_numbers: string | null;
    adult_count: number | null;
    child_count: number | null;
    contact_phone: string | null;
    cancel_reason: string | null;
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

// --- 날짜 헬퍼 (frontend/app/villa/page.tsx와 동일한 규칙) ---
const toISO = (d: Date) => {
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
};

const parseISO = (s: string) => {
    const [y, m, d] = s.split('-').map(Number);
    return new Date(y, m - 1, d);
};

const addDays = (d: Date, n: number) => {
    const next = new Date(d);
    next.setDate(next.getDate() + n);
    return next;
};

const shiftMonth = (year: number, month: number, delta: number) => {
    const i = year * 12 + (month - 1) + delta;
    return { year: Math.floor(i / 12), month: (i % 12) + 1 };
};

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

const STATUS_LABEL: Record<string, { label: string; cls: string }> = {
    confirmed: { label: '확정', cls: 'bg-blue-100 text-blue-700' },
    cancel_requested: { label: '취소 요청중', cls: 'bg-orange-100 text-orange-700' },
    applied: { label: '신청중', cls: 'bg-amber-100 text-amber-700' },
};

type DayEntry = { confirmed?: Application; pending: Application[] };

/** 한 달의 날짜별 점유 현황 맵. 점유 구간은 [체크인, 체크아웃)로 체크아웃 날은 비운다. */
function buildOccupancy(items: Application[], facilityId: number): Map<string, DayEntry> {
    const map = new Map<string, DayEntry>();
    for (const item of items) {
        if (item.facility_id !== facilityId) continue;
        const end = parseISO(item.end_date);
        for (let d = parseISO(item.start_date); d < end; d = addDays(d, 1)) {
            const key = toISO(d);
            const entry = map.get(key) ?? { pending: [] };
            if (item.status === 'confirmed' || item.status === 'cancel_requested') {
                entry.confirmed = item;
            } else {
                entry.pending.push(item);
            }
            map.set(key, entry);
        }
    }
    return map;
}

function MiniMonth({
    label, year, month, occupancy, onSelect,
}: {
    label: string; year: number; month: number;
    occupancy: Map<string, DayEntry>;
    onSelect: (entry: DayEntry) => void;
}) {
    const grid = useMemo(() => {
        const leading = new Date(year, month - 1, 1).getDay();
        const daysInMonth = new Date(year, month, 0).getDate();
        const cells: (Date | null)[] = Array(leading).fill(null);
        for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month - 1, d));
        while (cells.length % 7 !== 0) cells.push(null);
        return cells;
    }, [year, month]);

    return (
        <div className="rounded-xl border border-gray-100 p-2.5">
            <p className="text-sm font-bold text-gray-700 mb-2">{label} · {year}년 {month}월</p>
            <div className="grid grid-cols-7 gap-0.5 text-center">
                {WEEKDAYS.map((w, i) => (
                    <div key={w} className={`text-[10px] font-bold py-0.5 ${
                        i === 0 ? 'text-rose-400' : i === 6 ? 'text-blue-400' : 'text-gray-400'
                    }`}>
                        {w}
                    </div>
                ))}
                {grid.map((cell, idx) => {
                    if (!cell) return <div key={`e${idx}`} />;
                    const iso = toISO(cell);
                    const entry = occupancy.get(iso);
                    const bar = entry?.confirmed ?? entry?.pending[0];
                    const isBarStart = bar ? bar.start_date === iso : false;

                    return (
                        <button
                            key={iso}
                            disabled={!bar}
                            onClick={() => entry && onSelect(entry)}
                            className={`relative aspect-square flex flex-col items-center justify-start rounded text-[11px] pt-0.5 ${
                                bar ? 'hover:ring-1 hover:ring-blue-300 cursor-pointer' : ''
                            }`}
                        >
                            <span className="text-gray-700">{cell.getDate()}</span>
                            {bar && (
                                <span
                                    className={`w-full h-1 rounded-full mt-0.5 ${
                                        entry?.confirmed ? 'bg-blue-500' : 'bg-amber-400'
                                    }`}
                                />
                            )}
                            {bar && isBarStart && (
                                <span className="text-[9px] leading-tight text-gray-600 truncate w-full px-0.5">
                                    {bar.user_name}
                                    {!entry?.confirmed && entry && entry.pending.length > 1 && ` +${entry.pending.length - 1}`}
                                </span>
                            )}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

export default function AdminVillaPage() {
    const router = useRouter();
    const [data, setData] = useState<ApplicationsResponse | null>(null);
    const [cancels, setCancels] = useState<CancelRequest[]>([]);
    const [villas, setVillas] = useState<Villa[]>([]);
    const [selectedVillaId, setSelectedVillaId] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);
    const [busyId, setBusyId] = useState<number | null>(null);
    const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
    const [detail, setDetail] = useState<DayEntry | null>(null);

    const load = useCallback(async () => {
        try {
            const [apps, cancelList, villaList] = await Promise.all([
                call('/api/villa/admin/applications'),
                call('/api/villa/admin/cancel-requests'),
                getVillas(),
            ]);
            setData(apps);
            setCancels(cancelList);
            setVillas(villaList);
            setSelectedVillaId(prev => prev ?? villaList[0]?.id ?? null);
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
            await load();
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '처리에 실패했습니다.' });
        } finally {
            setBusyId(null);
        }
    };

    // 정규예약 대상월(data.year/month) 기준으로 세 달을 계산한다.
    const months = useMemo(() => {
        if (!data) return null;
        const target = { year: data.year, month: data.month };
        const open = shiftMonth(data.year, data.month, -1);
        const today = new Date();
        const current = { year: today.getFullYear(), month: today.getMonth() + 1 };
        return { current, open, target };
    }, [data]);

    const pendingFlat = useMemo(() => data?.groups.flatMap(g => g.applications) ?? [], [data]);
    const calendarItems = useMemo(() => [...(data?.confirmed ?? []), ...pendingFlat], [data, pendingFlat]);

    // 요약 카드의 '확정' 수치는 방금 만든 3개월 달력과 눈높이를 맞춘다(전체 누적이면 의미가 옅어진다).
    const confirmedInRange = useMemo(() => {
        if (!data || !months) return 0;
        const inRange = [months.current, months.open, months.target];
        return data.confirmed.filter(c => {
            const cy = Number(c.start_date.slice(0, 4));
            const cm = Number(c.start_date.slice(5, 7));
            return inRange.some(m => m.year === cy && m.month === cm);
        }).length;
    }, [data, months]);

    if (loading) {
        return <div className="p-8 text-center text-gray-500">불러오는 중...</div>;
    }

    return (
        <div className="space-y-6 px-4 sm:px-0">
            <div className="flex items-center gap-3">
                <button
                    onClick={() => router.push('/admin')}
                    className="p-2 rounded-full hover:bg-gray-100 transition-colors text-gray-500"
                >
                    <ArrowLeft size={20} />
                </button>
                <h2 className="text-xl font-bold text-gray-900">비트별장 예약 관리</h2>
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
                        { label: '확정 (아래 3개월)', value: confirmedInRange, cls: 'text-blue-600' },
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

            {/* 예약 현황 달력: 이번달 · 선착순예약월 · 예약신청대상월 */}
            {months && villas.length > 0 && (
                <section className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100">
                    <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                        <h3 className="font-bold text-gray-800 flex items-center gap-2">
                            <Calendar size={16} className="text-blue-600" /> 예약 현황
                        </h3>
                        <div className="flex gap-1.5">
                            {villas.map(v => (
                                <button
                                    key={v.id}
                                    onClick={() => setSelectedVillaId(v.id)}
                                    className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors ${
                                        v.id === selectedVillaId
                                            ? 'bg-blue-600 text-white'
                                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                                    }`}
                                >
                                    {v.name}
                                </button>
                            ))}
                        </div>
                    </div>

                    {selectedVillaId && (() => {
                        const occupancy = buildOccupancy(calendarItems, selectedVillaId);
                        return (
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                <MiniMonth label="이번달" year={months.current.year} month={months.current.month}
                                    occupancy={occupancy} onSelect={setDetail} />
                                <MiniMonth label="선착순예약월" year={months.open.year} month={months.open.month}
                                    occupancy={occupancy} onSelect={setDetail} />
                                <MiniMonth label="예약신청대상월" year={months.target.year} month={months.target.month}
                                    occupancy={occupancy} onSelect={setDetail} />
                            </div>
                        );
                    })()}

                    <div className="flex items-center justify-center gap-4 mt-3 pt-3 border-t border-gray-100 text-xs text-gray-500">
                        <span className="flex items-center gap-1.5">
                            <span className="w-3 h-1 rounded-full bg-blue-500" /> 확정
                        </span>
                        <span className="flex items-center gap-1.5">
                            <span className="w-3 h-1 rounded-full bg-amber-400" /> 신청중
                        </span>
                        <span>날짜를 클릭하면 예약 정보를 볼 수 있습니다</span>
                    </div>
                </section>
            )}

            {/* 신청 그룹 — 페이지에 표시 중인 달과 무관하게 전체를 보여준다 */}
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
                                            · {a.checkin_time} 입실{a.checkin_time_forced && (
                                                <span className="ml-1 text-[9px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full">정규</span>
                                            )}
                                            {' '}/ {a.checkout_time} 퇴실{a.checkout_time_forced && (
                                                <span className="ml-1 text-[9px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full">정규</span>
                                            )}
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

            {/* 예약 상세 모달 (달력에서 날짜 클릭) */}
            {detail && (
                <div
                    className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm p-4"
                    onClick={() => setDetail(null)}
                >
                    <div
                        className="bg-white w-full max-w-md rounded-3xl p-5 shadow-2xl max-h-[85vh] overflow-y-auto space-y-3"
                        onClick={e => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between">
                            <h2 className="font-bold text-gray-900">예약 정보</h2>
                            <button
                                onClick={() => setDetail(null)}
                                className="p-2 bg-gray-100 rounded-full hover:bg-gray-200 transition-colors"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        {[detail.confirmed, ...detail.pending].filter((a): a is Application => !!a).map(a => (
                            <div key={a.id} className="rounded-2xl border border-gray-100 p-4 text-sm space-y-1.5">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className="font-bold text-gray-900">{a.user_name}</span>
                                    {a.user_dept && <span className="text-gray-400">{a.user_dept}</span>}
                                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${STATUS_LABEL[a.status]?.cls ?? 'bg-gray-100 text-gray-600'}`}>
                                        {STATUS_LABEL[a.status]?.label ?? a.status}
                                    </span>
                                </div>
                                <p className="text-gray-600">{a.facility_name} · {a.start_date} ~ {a.end_date} ({a.nights}박)</p>
                                <p className="text-gray-500 flex items-center flex-wrap gap-x-1">
                                    <span>
                                        {a.checkin_time} 입실
                                        {a.checkin_time_forced && (
                                            <span className="ml-1 text-[9px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full">정규시간</span>
                                        )}
                                    </span>
                                    <span>·</span>
                                    <span>
                                        {a.checkout_time} 퇴실
                                        {a.checkout_time_forced && (
                                            <span className="ml-1 text-[9px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full">정규시간</span>
                                        )}
                                    </span>
                                </p>
                                <p className="text-gray-500">
                                    인원 {a.participant_count}명
                                    {(a.adult_count != null || a.child_count != null) && (
                                        <> (성인 {a.adult_count ?? '-'} · 아동 {a.child_count ?? '-'})</>
                                    )}
                                </p>
                                <p className="text-gray-500">
                                    차량 {a.vehicle_count != null ? `${a.vehicle_count}대` : '미입력'}
                                    {a.vehicle_numbers && ` (${a.vehicle_numbers})`}
                                </p>
                                <p className="text-gray-500">
                                    연락처 {a.contact_phone || '미입력'}
                                </p>
                                <p className="text-xs text-gray-400">
                                    최근 1년 {a.usage_count}회 이용 · 신청 {a.created_at ? new Date(a.created_at).toLocaleString('ko-KR') : '-'}
                                </p>
                                {a.cancel_reason && (
                                    <p className="text-xs text-orange-600 bg-orange-50 rounded-lg px-2 py-1">
                                        취소 사유: {a.cancel_reason}
                                    </p>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
