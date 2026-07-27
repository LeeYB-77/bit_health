'use client';
// 비트별장(청평별장/동비재) 예약 신청 화면. 달력으로 확정/신청중 예약을 구분해 보여준다.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
    ArrowLeft, Calendar, ChevronLeft, ChevronRight, Info, Users, X, Trash2, Loader2,
} from 'lucide-react';
import {
    getVillas, getVillaRound, getVillaCalendar, getMyVillaReservations,
    applyVilla, cancelVillaApplication, requestVillaCancel,
    Villa, VillaRound, VillaCalendarItem, VillaMyReservation, VillaStatus,
} from '@/lib/api';

// --- 날짜 헬퍼 ---
// toISOString()은 UTC로 변환해 KST 자정 근처에서 날짜가 밀린다. 로컬 기준으로 직접 만든다.
const toISO = (d: Date) => {
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
};

// new Date('2026-09-10')은 UTC 자정으로 파싱된다. 로컬 자정으로 명시 생성한다.
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
    const index = year * 12 + (month - 1) + delta;
    return { year: Math.floor(index / 12), month: (index % 12) + 1 };
};

/** 이용 기간이 걸치는 월 번호. 백엔드 months_spanned와 같은 규칙(체크아웃 월 포함). */
const monthsSpanned = (startISO: string, endISO: string) => {
    const start = parseISO(startISO);
    const end = parseISO(endISO);
    const months = new Set<number>();
    let y = start.getFullYear();
    let m = start.getMonth() + 1;
    while (y * 12 + m <= end.getFullYear() * 12 + end.getMonth() + 1) {
        months.add(m);
        const next = shiftMonth(y, m, 1);
        y = next.year;
        m = next.month;
    }
    return months;
};

const nightsBetween = (startISO: string, endISO: string) =>
    Math.round((parseISO(endISO).getTime() - parseISO(startISO).getTime()) / 86400000);

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

const STATUS_META: Record<VillaStatus, { label: string; cls: string }> = {
    applied: { label: '신청중', cls: 'bg-amber-100 text-amber-700' },
    confirmed: { label: '확정', cls: 'bg-blue-100 text-blue-700' },
    cancel_requested: { label: '취소 요청중', cls: 'bg-orange-100 text-orange-700' },
    canceled: { label: '취소됨', cls: 'bg-gray-100 text-gray-500' },
    rejected: { label: '미선정', cls: 'bg-gray-100 text-gray-500' },
};

type DayEntry = {
    blocking?: VillaCalendarItem;      // confirmed 또는 cancel_requested
    applied: VillaCalendarItem[];
    mineId?: number;
};

export default function VillaPage() {
    const router = useRouter();

    const [villas, setVillas] = useState<Villa[]>([]);
    const [selectedVillaId, setSelectedVillaId] = useState<number | null>(null);
    const [round, setRound] = useState<VillaRound | null>(null);
    const [items, setItems] = useState<VillaCalendarItem[]>([]);
    const [myList, setMyList] = useState<VillaMyReservation[]>([]);
    const [view, setView] = useState<{ year: number; month: number } | null>(null);

    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

    // 신청 모달
    const [applyOpen, setApplyOpen] = useState(false);
    const [form, setForm] = useState({
        start_date: '', end_date: '', checkin_time: '15:00', checkout_time: '11:00', participant_count: 4,
    });

    // 취소 요청 모달
    const [cancelTarget, setCancelTarget] = useState<VillaMyReservation | null>(null);
    const [cancelReason, setCancelReason] = useState('');

    const selectedVilla = villas.find(v => v.id === selectedVillaId) ?? null;

    useEffect(() => {
        if (!localStorage.getItem('access_token')) {
            router.replace('/login?redirect=/villa');
            return;
        }
        (async () => {
            try {
                const [villaList, roundInfo] = await Promise.all([getVillas(), getVillaRound()]);
                setVillas(villaList);
                setRound(roundInfo);
                setSelectedVillaId(villaList[0]?.id ?? null);
                // 기본 조회 월은 현재 접수중인 대상월
                setView({ year: roundInfo.target_year, month: roundInfo.target_month });
            } catch (e) {
                setMessage({ type: 'err', text: e instanceof Error ? e.message : '정보를 불러오지 못했습니다.' });
            } finally {
                setLoading(false);
            }
        })();
    }, [router]);

    const reload = useCallback(async () => {
        if (!selectedVillaId || !view) return;
        try {
            const [calendar, mine] = await Promise.all([
                getVillaCalendar(selectedVillaId, view.year, view.month),
                getMyVillaReservations(),
            ]);
            setItems(calendar.items);
            setMyList(mine);
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '예약 현황을 불러오지 못했습니다.' });
        }
    }, [selectedVillaId, view]);

    useEffect(() => { reload(); }, [reload]);

    // 날짜별 점유 상태. 점유 일수는 [체크인, 체크아웃) — 체크아웃 날은 다음 팀이 입실할 수 있어 비운다.
    const occupancy = useMemo(() => {
        const map = new Map<string, DayEntry>();
        for (const item of items) {
            const end = parseISO(item.end_date);
            for (let d = parseISO(item.start_date); d < end; d = addDays(d, 1)) {
                const key = toISO(d);
                const entry = map.get(key) ?? { applied: [] };
                if (item.status === 'confirmed' || item.status === 'cancel_requested') {
                    entry.blocking = item;
                } else {
                    entry.applied.push(item);
                }
                if (item.is_mine) entry.mineId = item.id;
                map.set(key, entry);
            }
        }
        return map;
    }, [items]);

    const grid = useMemo(() => {
        if (!view) return [];
        const { year, month } = view;
        const leading = new Date(year, month - 1, 1).getDay();
        const daysInMonth = new Date(year, month, 0).getDate();
        const cells: (Date | null)[] = Array(leading).fill(null);
        for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month - 1, d));
        while (cells.length % 7 !== 0) cells.push(null);
        return cells;
    }, [view]);

    const isTargetMonth = !!(round && view && round.target_year === view.year && round.target_month === view.month);
    const todayISO = toISO(new Date());

    const openApply = (dayISO: string) => {
        setForm({
            start_date: dayISO,
            end_date: toISO(addDays(parseISO(dayISO), 1)),
            checkin_time: selectedVilla?.default_checkin_time || '15:00',
            checkout_time: selectedVilla?.default_checkout_time || '11:00',
            participant_count: 4,
        });
        setMessage(null);
        setApplyOpen(true);
    };

    // 성수기 제한을 프론트에서도 미리 알려준다. 최종 검증은 서버가 한다.
    const formNights = form.start_date && form.end_date ? nightsBetween(form.start_date, form.end_date) : 0;
    const formPeakLimit = useMemo(() => {
        if (!round?.peak_max_nights || !form.start_date || !form.end_date || formNights <= 0) return null;
        const spanned = monthsSpanned(form.start_date, form.end_date);
        const hitsPeak = round.peak_months.some(m => spanned.has(m));
        return hitsPeak ? round.peak_max_nights : null;
    }, [round, form.start_date, form.end_date, formNights]);

    const formError = (() => {
        if (!form.start_date || !form.end_date) return '날짜를 선택해 주세요.';
        if (formNights < 1) return '체크아웃 날짜는 체크인 날짜보다 뒤여야 합니다.';
        if (form.participant_count < 1) return '사용 인원을 입력해 주세요.';
        if (selectedVilla && form.participant_count > selectedVilla.capacity)
            return `${selectedVilla.name}의 정원은 ${selectedVilla.capacity}명입니다.`;
        if (formPeakLimit && formNights > formPeakLimit)
            return `성수기(${round?.peak_months.join('·')}월)가 포함된 기간은 최대 ${formPeakLimit}박까지 가능합니다.`;
        return null;
    })();

    const submitApply = async () => {
        if (!selectedVillaId || formError) return;
        setSubmitting(true);
        try {
            await applyVilla({ facility_id: selectedVillaId, ...form });
            setApplyOpen(false);
            setMessage({ type: 'ok', text: '예약을 신청했습니다. 확정 결과는 마감일에 안내됩니다.' });
            await reload();
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '신청에 실패했습니다.' });
        } finally {
            setSubmitting(false);
        }
    };

    const handleCancelApplied = async (id: number) => {
        setSubmitting(true);
        try {
            await cancelVillaApplication(id);
            setMessage({ type: 'ok', text: '신청을 취소했습니다.' });
            await reload();
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '취소에 실패했습니다.' });
        } finally {
            setSubmitting(false);
        }
    };

    const submitCancelRequest = async () => {
        if (!cancelTarget) return;
        setSubmitting(true);
        try {
            await requestVillaCancel(cancelTarget.id, cancelReason.trim() || null);
            setCancelTarget(null);
            setCancelReason('');
            setMessage({ type: 'ok', text: '취소 요청이 접수되었습니다. 관리자 승인 후 취소됩니다.' });
            await reload();
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '취소 요청에 실패했습니다.' });
        } finally {
            setSubmitting(false);
        }
    };

    if (loading) return (
        <div className="h-screen flex items-center justify-center bg-gray-50">
            <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
        </div>
    );

    return (
        <div className="min-h-screen bg-gray-50 font-sans text-gray-900 pb-10">
            <header className="bg-white p-4 shadow-sm flex items-center gap-4 sticky top-0 z-10">
                <button onClick={() => router.push('/')} className="text-gray-600">
                    <ArrowLeft />
                </button>
                <h1 className="text-lg font-bold text-gray-900">비트별장 예약</h1>
            </header>

            <main className="p-4 space-y-5 max-w-lg mx-auto">
                {message && (
                    <div className={`rounded-xl p-3 text-sm flex items-start gap-2 ${
                        message.type === 'ok'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-100'
                            : 'bg-rose-50 text-rose-700 border border-rose-100'
                    }`}>
                        <span className="flex-1">{message.text}</span>
                        <button onClick={() => setMessage(null)} className="shrink-0 opacity-60 hover:opacity-100">
                            <X size={16} />
                        </button>
                    </div>
                )}

                {villas.length === 0 ? (
                    <div className="rounded-2xl bg-white p-8 text-center text-gray-400 border border-gray-100 border-dashed">
                        등록된 별장이 없습니다.
                    </div>
                ) : (
                    <>
                        {/* 별장 선택 */}
                        <div className="grid grid-cols-2 gap-2 bg-white p-1.5 rounded-2xl shadow-sm border border-gray-100">
                            {villas.map(v => (
                                <button
                                    key={v.id}
                                    onClick={() => setSelectedVillaId(v.id)}
                                    className={`rounded-xl py-2.5 text-sm font-bold transition-all ${
                                        v.id === selectedVillaId
                                            ? 'bg-blue-600 text-white shadow'
                                            : 'text-gray-500 hover:bg-gray-50'
                                    }`}
                                >
                                    {v.name}
                                    <span className={`block text-[10px] font-normal mt-0.5 ${
                                        v.id === selectedVillaId ? 'text-blue-100' : 'text-gray-400'
                                    }`}>
                                        정원 {v.capacity}명
                                    </span>
                                </button>
                            ))}
                        </div>

                        {/* 회차 안내 */}
                        {round && (
                            <div className="rounded-2xl bg-blue-50 border border-blue-100 p-4 text-sm">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="font-bold text-blue-800 flex items-center gap-2">
                                        <Calendar size={16} />
                                        {round.target_year}년 {round.target_month}월 예약 접수중
                                    </span>
                                    <span className="text-xs font-bold text-blue-600 bg-blue-100 px-2 py-1 rounded-full shrink-0">
                                        {round.days_left > 0 ? `D-${round.days_left}` : '오늘 마감'}
                                    </span>
                                </div>
                                <p className="text-xs text-blue-700 mt-2 leading-relaxed">
                                    {round.apply_end} 마감 후 확정 결과를 Slack·메일로 안내합니다.
                                    {round.peak_max_nights && round.peak_months.length > 0 && (
                                        <> 성수기({round.peak_months.join('·')}월)가 포함된 기간은 최대 {round.peak_max_nights}박까지 가능합니다.</>
                                    )}
                                </p>
                            </div>
                        )}

                        {/* 달력 */}
                        <div className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <div className="flex items-center justify-between mb-3">
                                <button
                                    onClick={() => view && setView(shiftMonth(view.year, view.month, -1))}
                                    className="p-1.5 text-gray-400 hover:text-blue-600 transition-colors"
                                >
                                    <ChevronLeft size={20} />
                                </button>
                                <span className="font-bold text-gray-800">
                                    {view?.year}년 {view?.month}월
                                </span>
                                <button
                                    onClick={() => view && setView(shiftMonth(view.year, view.month, 1))}
                                    className="p-1.5 text-gray-400 hover:text-blue-600 transition-colors"
                                >
                                    <ChevronRight size={20} />
                                </button>
                            </div>

                            {!isTargetMonth && (
                                <p className="text-xs text-gray-500 bg-gray-50 rounded-lg p-2.5 mb-3 flex items-start gap-1.5">
                                    <Info size={14} className="mt-0.5 shrink-0" />
                                    이 달은 현재 접수 대상이 아닙니다. 조회만 가능합니다.
                                </p>
                            )}

                            <div className="grid grid-cols-7 gap-1 text-center">
                                {WEEKDAYS.map((w, i) => (
                                    <div key={w} className={`text-[11px] font-bold py-1 ${
                                        i === 0 ? 'text-rose-400' : i === 6 ? 'text-blue-400' : 'text-gray-400'
                                    }`}>
                                        {w}
                                    </div>
                                ))}

                                {grid.map((cell, idx) => {
                                    if (!cell) return <div key={`e${idx}`} />;

                                    const iso = toISO(cell);
                                    const entry = occupancy.get(iso);
                                    const isPast = iso < todayISO;
                                    const blocked = !!entry?.blocking;
                                    const appliedCount = entry?.applied.length ?? 0;
                                    const isMine = !!entry?.mineId;
                                    const selectable = isTargetMonth && !isPast && !blocked;

                                    // 기간의 시작/끝에만 라운딩을 주면 연박이 하나의 bar로 읽힌다.
                                    const bar = entry?.blocking ?? entry?.applied[0];
                                    const lastOccupied = bar ? toISO(addDays(parseISO(bar.end_date), -1)) : null;
                                    const isBarStart = bar ? iso === bar.start_date : false;
                                    const isBarEnd = bar ? iso === lastOccupied : false;

                                    return (
                                        <button
                                            key={iso}
                                            disabled={!selectable}
                                            onClick={() => openApply(iso)}
                                            className={`relative aspect-square flex flex-col items-center justify-center rounded-lg text-xs transition-all ${
                                                isPast ? 'text-gray-300'
                                                    : selectable ? 'text-gray-800 hover:bg-blue-50 active:scale-95'
                                                        : 'text-gray-500 cursor-not-allowed'
                                            }`}
                                        >
                                            <span className={`font-bold ${isMine ? 'text-emerald-700' : ''}`}>
                                                {cell.getDate()}
                                            </span>

                                            {bar && (
                                                <span
                                                    className={`absolute bottom-1 left-0 right-0 h-1.5 ${
                                                        blocked ? 'bg-blue-500' : 'bg-amber-300'
                                                    } ${isBarStart ? 'rounded-l-full ml-1' : ''} ${isBarEnd ? 'rounded-r-full mr-1' : ''}`}
                                                />
                                            )}

                                            {!blocked && appliedCount > 0 && (
                                                <span className="text-[9px] text-amber-600 font-bold leading-none mt-0.5">
                                                    {appliedCount}팀
                                                </span>
                                            )}
                                            {isMine && (
                                                <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                            )}
                                        </button>
                                    );
                                })}
                            </div>

                            {/* 범례 */}
                            <div className="flex items-center justify-center gap-4 mt-4 pt-3 border-t border-gray-100 text-[11px] text-gray-500">
                                <span className="flex items-center gap-1.5">
                                    <span className="w-3 h-1.5 rounded-full bg-blue-500" /> 확정
                                </span>
                                <span className="flex items-center gap-1.5">
                                    <span className="w-3 h-1.5 rounded-full bg-amber-300" /> 신청중
                                </span>
                                <span className="flex items-center gap-1.5">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> 내 신청
                                </span>
                            </div>
                        </div>

                        {/* 이 달 예약 목록 */}
                        {items.length > 0 && (
                            <div className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                                <h2 className="text-sm font-bold text-gray-800 mb-3">
                                    {view?.month}월 예약 현황
                                </h2>
                                <ul className="space-y-2">
                                    {items.map(item => (
                                        <li key={item.id} className={`rounded-xl p-3 text-xs border ${
                                            item.is_mine ? 'bg-emerald-50 border-emerald-100' : 'bg-gray-50 border-gray-100'
                                        }`}>
                                            <div className="flex items-center justify-between gap-2">
                                                <span className="font-bold text-gray-800">
                                                    {item.start_date} ~ {item.end_date}
                                                    <span className="text-gray-400 font-normal ml-1">{item.nights}박</span>
                                                </span>
                                                <span className={`px-2 py-0.5 rounded-full font-bold shrink-0 ${STATUS_META[item.status].cls}`}>
                                                    {item.is_mine ? '내 신청' : STATUS_META[item.status].label}
                                                </span>
                                            </div>
                                            <p className="text-gray-500 mt-1">
                                                {item.user_name
                                                    ? `${item.user_name}${item.user_dept ? ` · ${item.user_dept}` : ''} · ${item.participant_count}명`
                                                    : `신청 접수됨 · ${item.participant_count}명`}
                                            </p>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {/* 내 신청 현황 */}
                        <div className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <h2 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
                                <Users size={16} className="text-blue-600" /> 내 신청 현황
                            </h2>
                            {myList.length === 0 ? (
                                <div className="text-center py-8 text-gray-400 bg-gray-50 rounded-xl border border-gray-100 border-dashed text-sm">
                                    신청 내역이 없습니다.
                                </div>
                            ) : (
                                <ul className="space-y-3">
                                    {myList.map(r => (
                                        <li key={r.id} className="border border-gray-100 rounded-xl p-3.5">
                                            <div className="flex items-start justify-between gap-2">
                                                <div className="min-w-0">
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        <span className="font-bold text-gray-800 text-sm">{r.facility_name}</span>
                                                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${STATUS_META[r.status].cls}`}>
                                                            {STATUS_META[r.status].label}
                                                        </span>
                                                        {r.needs_extra_info && (
                                                            <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-purple-100 text-purple-700">
                                                                추가입력 필요
                                                            </span>
                                                        )}
                                                    </div>
                                                    <p className="text-xs text-gray-600 mt-1.5">
                                                        {r.start_date} ~ {r.end_date} ({r.nights}박)
                                                    </p>
                                                    <p className="text-xs text-gray-400 mt-0.5">
                                                        {r.checkin_time} 입실 · {r.checkout_time} 퇴실 · {r.participant_count}명
                                                    </p>
                                                    {r.status === 'cancel_requested' && (
                                                        <p className="text-[11px] text-orange-600 mt-1.5">
                                                            관리자 승인 대기 중입니다.
                                                        </p>
                                                    )}
                                                </div>

                                                {r.status === 'applied' && (
                                                    <button
                                                        onClick={() => handleCancelApplied(r.id)}
                                                        disabled={submitting}
                                                        className="p-2 text-gray-400 hover:text-rose-500 transition-colors shrink-0 disabled:opacity-40"
                                                        title="신청 취소"
                                                    >
                                                        <Trash2 size={16} />
                                                    </button>
                                                )}
                                                {r.status === 'confirmed' && (
                                                    <button
                                                        onClick={() => { setCancelTarget(r); setCancelReason(''); }}
                                                        className="text-[11px] font-bold text-rose-600 border border-rose-200 rounded-lg px-2 py-1 hover:bg-rose-50 transition-colors shrink-0"
                                                    >
                                                        취소 요청
                                                    </button>
                                                )}
                                            </div>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                    </>
                )}
            </main>

            {/* 신청 모달 */}
            {applyOpen && selectedVilla && (
                <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <div className="bg-white w-full max-w-md rounded-3xl p-5 shadow-2xl max-h-[90vh] overflow-y-auto">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="font-bold text-gray-900">{selectedVilla.name} 예약 신청</h2>
                            <button
                                onClick={() => setApplyOpen(false)}
                                className="p-2 bg-gray-100 rounded-full hover:bg-gray-200 transition-colors"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        <div className="space-y-3">
                            <div className="grid grid-cols-2 gap-3">
                                <label className="block">
                                    <span className="text-xs font-bold text-gray-600">체크인</span>
                                    <input
                                        type="date"
                                        value={form.start_date}
                                        onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
                                        className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </label>
                                <label className="block">
                                    <span className="text-xs font-bold text-gray-600">체크아웃</span>
                                    <input
                                        type="date"
                                        value={form.end_date}
                                        onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
                                        className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </label>
                            </div>

                            {formNights > 0 && (
                                <p className="text-xs text-blue-700 bg-blue-50 rounded-lg px-3 py-2">
                                    {formNights}박 {formNights + 1}일
                                    {formPeakLimit && <span className="text-blue-500"> · 성수기 최대 {formPeakLimit}박</span>}
                                </p>
                            )}

                            <div className="grid grid-cols-2 gap-3">
                                <label className="block">
                                    <span className="text-xs font-bold text-gray-600">예상 입실 시간</span>
                                    <input
                                        type="time"
                                        value={form.checkin_time}
                                        onChange={e => setForm(f => ({ ...f, checkin_time: e.target.value }))}
                                        className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </label>
                                <label className="block">
                                    <span className="text-xs font-bold text-gray-600">예상 퇴실 시간</span>
                                    <input
                                        type="time"
                                        value={form.checkout_time}
                                        onChange={e => setForm(f => ({ ...f, checkout_time: e.target.value }))}
                                        className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </label>
                            </div>

                            <label className="block">
                                <span className="text-xs font-bold text-gray-600">
                                    사용 인원 (최대 {selectedVilla.capacity}명)
                                </span>
                                <input
                                    type="number"
                                    min={1}
                                    max={selectedVilla.capacity}
                                    value={form.participant_count}
                                    onChange={e => setForm(f => ({ ...f, participant_count: Number(e.target.value) }))}
                                    className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                                />
                            </label>

                            <p className="text-[11px] text-gray-500 bg-gray-50 rounded-lg px-3 py-2 leading-relaxed">
                                같은 기간에 여러 명이 신청할 수 있습니다. 중복 시 관리자가 확정자를 선정하며,
                                결과는 마감일에 Slack·메일로 안내됩니다.
                            </p>

                            {formError && (
                                <p className="text-xs text-rose-600 font-medium">{formError}</p>
                            )}

                            <button
                                onClick={submitApply}
                                disabled={!!formError || submitting}
                                className="w-full bg-blue-600 text-white font-bold py-3 rounded-xl disabled:bg-gray-300 disabled:cursor-not-allowed hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
                            >
                                {submitting ? <Loader2 size={18} className="animate-spin" /> : '신청하기'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* 취소 요청 모달 */}
            {cancelTarget && (
                <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <div className="bg-white w-full max-w-md rounded-3xl p-5 shadow-2xl">
                        <div className="flex items-center justify-between mb-3">
                            <h2 className="font-bold text-gray-900">예약 취소 요청</h2>
                            <button
                                onClick={() => setCancelTarget(null)}
                                className="p-2 bg-gray-100 rounded-full hover:bg-gray-200 transition-colors"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        <p className="text-sm text-gray-600">
                            {cancelTarget.facility_name} {cancelTarget.start_date} ~ {cancelTarget.end_date}
                        </p>
                        <p className="text-xs text-gray-500 mt-2 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                            확정된 예약은 관리자 승인 후 취소됩니다. 승인 전까지는 예약이 유지됩니다.
                        </p>

                        <label className="block mt-3">
                            <span className="text-xs font-bold text-gray-600">취소 사유 (선택)</span>
                            <textarea
                                rows={3}
                                value={cancelReason}
                                onChange={e => setCancelReason(e.target.value)}
                                placeholder="예) 개인 사정으로 일정이 변경되었습니다."
                                className="mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                            />
                        </label>

                        <button
                            onClick={submitCancelRequest}
                            disabled={submitting}
                            className="w-full mt-3 bg-rose-600 text-white font-bold py-3 rounded-xl disabled:bg-gray-300 hover:bg-rose-700 transition-colors flex items-center justify-center gap-2"
                        >
                            {submitting ? <Loader2 size={18} className="animate-spin" /> : '취소 요청하기'}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
