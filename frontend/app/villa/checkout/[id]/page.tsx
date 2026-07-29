'use client';
// 비트별장 퇴실 체크사항 페이지. 퇴실일 오전 Slack 링크로 진입해 체크박스로 확인하고 제출한다.
// 제출 결과(체크 완료 항목·특이사항)는 슬랙으로 빌라 관리자에게 전달된다.

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AlertTriangle, ArrowLeft, CheckCircle2, Loader2, X } from 'lucide-react';
import { getVillaCheckout, submitVillaCheckout, VillaCheckout } from '@/lib/api';

export default function VillaCheckoutPage() {
    const router = useRouter();
    const params = useParams<{ id: string }>();
    const reservationId = Number(params?.id);

    const [data, setData] = useState<VillaCheckout | null>(null);
    const [checked, setChecked] = useState<boolean[]>([]);
    const [notes, setNotes] = useState('');

    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [done, setDone] = useState(false);

    const load = useCallback(async () => {
        try {
            const result = await getVillaCheckout(reservationId);
            setData(result);
            setChecked(result.checked ?? result.checklist.map(() => false));
            setNotes(result.notes ?? '');
            setDone(result.submitted);
        } catch (e) {
            setError(e instanceof Error ? e.message : '퇴실 체크사항을 불러오지 못했습니다.');
        } finally {
            setLoading(false);
        }
    }, [reservationId]);

    useEffect(() => {
        if (!localStorage.getItem('access_token')) {
            router.replace(`/login?redirect=/villa/checkout/${reservationId}`);
            return;
        }
        if (!Number.isFinite(reservationId)) {
            setError('잘못된 예약 번호입니다.');
            setLoading(false);
            return;
        }
        load();
    }, [load, reservationId, router]);

    const toggle = (idx: number) => {
        setChecked(prev => prev.map((v, i) => (i === idx ? !v : v)));
    };

    const allChecked = checked.length > 0 && checked.every(Boolean);

    const submit = async () => {
        setSubmitting(true);
        setError(null);
        try {
            await submitVillaCheckout(reservationId, { checked, notes: notes.trim() || null });
            setDone(true);
        } catch (e) {
            setError(e instanceof Error ? e.message : '제출에 실패했습니다.');
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
                <button onClick={() => router.push('/villa')} className="text-gray-600">
                    <ArrowLeft />
                </button>
                <h1 className="text-lg font-bold text-gray-900">
                    {data ? `${data.reservation.facility_name} 퇴실 체크사항` : '퇴실 체크사항'}
                </h1>
            </header>

            <main className="p-4 space-y-4 max-w-lg mx-auto">
                {error && (
                    <div className="rounded-xl bg-rose-50 border border-rose-100 p-3 text-sm text-rose-700 flex items-start gap-2">
                        <span className="flex-1">{error}</span>
                        <button onClick={() => setError(null)}><X size={16} /></button>
                    </div>
                )}

                {data && (
                    <>
                        <section className="rounded-xl bg-rose-50 border border-rose-100 p-3 text-xs font-bold text-rose-700 flex items-center gap-2">
                            <AlertTriangle size={16} className="shrink-0" />
                            위반 사항 시 패널티(범칙금 3만원) 부과
                        </section>

                        {done && (
                            <section className="rounded-xl bg-emerald-50 border border-emerald-100 p-3 text-sm text-emerald-700 flex items-center gap-2">
                                <CheckCircle2 size={18} className="shrink-0" />
                                퇴실 체크사항을 제출했습니다. 안전히 귀가하세요!
                            </section>
                        )}

                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <h2 className="text-xs font-bold text-blue-600 uppercase tracking-wide mb-3">
                                순서대로 확인 후 체크
                            </h2>
                            <ul className="space-y-2.5">
                                {data.checklist.map((item, idx) => (
                                    <li key={idx}>
                                        <label className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-colors ${
                                            checked[idx]
                                                ? 'bg-emerald-50 border-emerald-200'
                                                : 'bg-amber-50 border-amber-100'
                                        } ${done ? 'opacity-70 pointer-events-none' : ''}`}>
                                            <input
                                                type="checkbox"
                                                checked={!!checked[idx]}
                                                onChange={() => toggle(idx)}
                                                disabled={done}
                                                className="mt-0.5 w-5 h-5 shrink-0 accent-emerald-600"
                                            />
                                            <span className="text-sm">
                                                <span className="font-bold text-gray-800">{idx + 1}. {item.label}</span>
                                                {item.sub && <span className="block text-xs text-gray-500 mt-0.5">{item.sub}</span>}
                                            </span>
                                        </label>
                                    </li>
                                ))}
                            </ul>
                        </section>

                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <h2 className="text-xs font-bold text-blue-600 uppercase tracking-wide mb-2">특이사항</h2>
                            <textarea
                                value={notes}
                                onChange={e => setNotes(e.target.value)}
                                disabled={done}
                                rows={4}
                                placeholder="파손된 집기, 남은 문제 등이 있으면 적어주세요. (선택)"
                                className="w-full rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm outline-none focus:ring-2 focus:ring-blue-500 resize-none disabled:opacity-70"
                            />
                        </section>

                        <p className="text-center text-xs text-gray-400">{data.key_return_notice}</p>
                        <p className="text-center text-xs text-gray-400">{data.emergency_contact}</p>

                        {!done && (
                            <button
                                onClick={submit}
                                disabled={submitting}
                                className="w-full bg-blue-600 text-white font-bold py-3 rounded-xl hover:bg-blue-700 disabled:bg-gray-300 flex items-center justify-center gap-2"
                            >
                                {submitting
                                    ? <Loader2 size={18} className="animate-spin" />
                                    : allChecked ? '체크사항 제출하기' : `제출하기 (${checked.filter(Boolean).length}/${data.checklist.length} 완료)`}
                            </button>
                        )}
                    </>
                )}
            </main>
        </div>
    );
}
