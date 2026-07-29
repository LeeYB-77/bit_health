'use client';
// 비트별장 이용안내 페이지. 입실 전날 메일·Slack 링크로 진입한다.

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Image from 'next/image';
import { ArrowLeft, Key, MapPin, Phone, Wifi, X } from 'lucide-react';
import { getVillaGuide, VillaAccessStep, VillaGuide } from '@/lib/api';

const ICON_SRC: Record<'key' | 'bellhop' | 'bell', string> = {
    key: '/villas/icons/icon-key.png',
    bellhop: '/villas/icons/icon-bellhop.jpg',
    bell: '/villas/icons/icon-bell.png',
};

function AccessStepView({ step }: { step: VillaAccessStep }) {
    if ('icon' in step) {
        return (
            <span className="w-7 h-7 rounded-lg bg-gray-900 p-1 shrink-0">
                <Image src={ICON_SRC[step.icon]} alt="" width={22} height={22} className="w-full h-full object-contain" />
            </span>
        );
    }
    return (
        <span className="font-extrabold text-blue-600 bg-blue-50 border border-blue-100 rounded-lg px-2.5 py-1 text-sm tracking-wide shrink-0">
            {step.code}
        </span>
    );
}

export default function VillaGuidePage() {
    const router = useRouter();
    const params = useParams<{ id: string }>();
    const reservationId = Number(params?.id);

    const [guide, setGuide] = useState<VillaGuide | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setGuide(await getVillaGuide(reservationId));
        } catch (e) {
            setError(e instanceof Error ? e.message : '이용안내를 불러오지 못했습니다.');
        } finally {
            setLoading(false);
        }
    }, [reservationId]);

    useEffect(() => {
        if (!localStorage.getItem('access_token')) {
            router.replace(`/login?redirect=/villa/guide/${reservationId}`);
            return;
        }
        if (!Number.isFinite(reservationId)) {
            setError('잘못된 예약 번호입니다.');
            setLoading(false);
            return;
        }
        load();
    }, [load, reservationId, router]);

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
                    {guide ? `${guide.reservation.facility_name} 이용안내` : '이용안내'}
                </h1>
            </header>

            <main className="p-4 space-y-4 max-w-lg mx-auto">
                {error && (
                    <div className="rounded-xl bg-rose-50 border border-rose-100 p-3 text-sm text-rose-700 flex items-start gap-2">
                        <span className="flex-1">{error}</span>
                        <button onClick={() => setError(null)}><X size={16} /></button>
                    </div>
                )}

                {guide && (
                    <>
                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <p className="text-sm text-gray-600">
                                {guide.reservation.start_date} ~ {guide.reservation.end_date}
                            </p>
                            <p className="text-xs text-gray-400 mt-0.5">
                                {guide.reservation.checkin_time} 입실 · {guide.reservation.checkout_time} 퇴실 ·
                                {' '}{guide.reservation.participant_count}명
                            </p>
                        </section>

                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <h2 className="text-xs font-bold text-blue-600 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                                <MapPin size={14} /> 위치
                            </h2>
                            <p className="text-sm">{guide.address}</p>
                            <p className="text-xs text-gray-400 mt-1">{guide.address_note}</p>
                        </section>

                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <h2 className="text-xs font-bold text-blue-600 uppercase tracking-wide mb-3 flex items-center gap-1.5">
                                <Key size={14} /> 출입방법
                            </h2>
                            <div className="space-y-3">
                                {guide.access.map((line, idx) => (
                                    <div key={idx} className={idx > 0 ? 'pt-3 border-t border-dashed border-gray-100' : ''}>
                                        <p className="text-xs text-gray-400 mb-1.5">{line.label}</p>
                                        {line.plain ? (
                                            <p className="text-sm font-bold">{line.plain}</p>
                                        ) : (
                                            <div className="flex items-center gap-1.5 flex-wrap">
                                                {line.steps!.map((step, i) => (
                                                    <span key={i} className="flex items-center gap-1.5">
                                                        {i > 0 && <span className="text-gray-300 text-xs">→</span>}
                                                        <AccessStepView step={step} />
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </section>

                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <h2 className="text-xs font-bold text-blue-600 uppercase tracking-wide mb-2">이용 안내</h2>
                            <ul className="space-y-2">
                                {guide.notes.map((n, i) => (
                                    <li key={i} className="text-sm text-gray-700 pl-3 relative before:content-[''] before:absolute before:left-0 before:top-2 before:w-1 before:h-1 before:rounded-full before:bg-gray-400">
                                        {n}
                                    </li>
                                ))}
                            </ul>
                        </section>

                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <h2 className="text-xs font-bold text-blue-600 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                                <Wifi size={14} /> 와이파이
                            </h2>
                            <p className="text-sm">{guide.wifi.network}</p>
                            <p className="text-xs text-gray-400 mt-0.5">비밀번호 {guide.wifi.password}</p>
                        </section>

                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <h2 className="text-xs font-bold text-blue-600 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                                <Key size={14} /> KEY 반납
                            </h2>
                            <p className="text-sm">{guide.key_return_notice}</p>
                        </section>

                        <p className="text-center text-xs text-gray-400 flex items-center justify-center gap-1.5">
                            <Phone size={12} /> {guide.emergency_contact}
                        </p>
                    </>
                )}
            </main>
        </div>
    );
}
