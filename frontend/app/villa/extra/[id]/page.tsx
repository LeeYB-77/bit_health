'use client';
// 비트별장 확정 예약의 추가 입력사항(차량, 이용 구성) 페이지. 확정 메일·Slack 링크로 진입한다.

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AlertTriangle, ArrowLeft, Car, CheckCircle, Loader2, Mail, Phone, Users, X } from 'lucide-react';
import {
    getVillaExtraInfo, saveVillaExtraInfo, sendVillaParkingMail, VillaExtraInfo, VillaParkingMail,
} from '@/lib/api';

const MAX_VEHICLES = 10;

export default function VillaExtraInfoPage() {
    const router = useRouter();
    const params = useParams<{ id: string }>();
    const reservationId = Number(params?.id);

    const [info, setInfo] = useState<VillaExtraInfo | null>(null);
    const [vehicleCount, setVehicleCount] = useState(0);
    const [vehicleNumbers, setVehicleNumbers] = useState<string[]>([]);
    const [adultCount, setAdultCount] = useState(0);
    const [childCount, setChildCount] = useState(0);
    const [contactPhone, setContactPhone] = useState('');

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState<{ warning: string | null; mailSent?: string } | null>(null);

    // 주차등록 요청 메일 — 저장 직후 내용을 확인·수정한 뒤 발송한다(속초별장만).
    const [parkingMail, setParkingMail] = useState<VillaParkingMail | null>(null);
    const [sending, setSending] = useState(false);

    const load = useCallback(async () => {
        try {
            const data = await getVillaExtraInfo(reservationId);
            setInfo(data);
            const count = data.vehicle_count ?? 0;
            setVehicleCount(count);
            setVehicleNumbers(
                (data.vehicle_numbers ?? '').split(',').map(s => s.trim()).filter(Boolean)
            );
            // 처음 들어온 경우 신청 인원을 성인 기본값으로 채워 입력 부담을 줄인다.
            setAdultCount(data.adult_count ?? (data.submitted ? 0 : data.participant_count));
            setChildCount(data.child_count ?? 0);
            setContactPhone(data.contact_phone ?? '');
        } catch (e) {
            setError(e instanceof Error ? e.message : '예약 정보를 불러오지 못했습니다.');
        } finally {
            setLoading(false);
        }
    }, [reservationId]);

    useEffect(() => {
        if (!localStorage.getItem('access_token')) {
            router.replace(`/login?redirect=/villa/extra/${reservationId}`);
            return;
        }
        if (!Number.isFinite(reservationId)) {
            setError('잘못된 예약 번호입니다.');
            setLoading(false);
            return;
        }
        load();
    }, [load, reservationId, router]);

    const setCount = (next: number) => {
        const clamped = Math.max(0, Math.min(MAX_VEHICLES, next));
        setVehicleCount(clamped);
        setVehicleNumbers(prev => {
            const copy = [...prev];
            copy.length = clamped;
            return Array.from(copy, v => v ?? '');
        });
    };

    const total = adultCount + childCount;
    const mismatch = !!info && total !== info.participant_count;
    const contactPhoneMissing = contactPhone.trim() === '';

    // 저장이 끝나면 입력 화면을 닫는다. 결과를 잠깐 보여준 뒤 예약 목록으로 돌아간다.
    const closeSoon = (delay = 1200) => {
        setTimeout(() => router.push('/villa'), delay);
    };

    const save = async () => {
        if (!info || contactPhoneMissing) return;
        setSaving(true);
        setError(null);
        setSaved(null);
        try {
            const result = await saveVillaExtraInfo(info.id, {
                vehicle_count: vehicleCount,
                vehicle_numbers: vehicleNumbers.map(v => v.trim()).filter(Boolean).join(', ') || null,
                adult_count: adultCount,
                child_count: childCount,
                contact_phone: contactPhone.trim(),
            });
            setSaved({ warning: result.warning ?? null });
            setInfo(result);
            if (result.parking_mail) {
                setParkingMail(result.parking_mail);
            } else {
                closeSoon();
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : '저장에 실패했습니다.');
        } finally {
            setSaving(false);
        }
    };

    const sendParkingMail = async () => {
        if (!info || !parkingMail) return;
        setSending(true);
        setError(null);
        try {
            const res = await sendVillaParkingMail(info.id, {
                subject: parkingMail.subject,
                body: parkingMail.body,
            });
            setParkingMail(null);
            setSaved(prev => ({ warning: prev?.warning ?? null, mailSent: res.message }));
            closeSoon(2000);
        } catch (e) {
            setError(e instanceof Error ? e.message : '메일 발송에 실패했습니다.');
        } finally {
            setSending(false);
        }
    };

    // 발송하지 않고 닫는 것도 허용한다 — 입력 내용은 이미 저장됐다.
    const skipParkingMail = () => {
        setParkingMail(null);
        closeSoon();
    };

    if (loading) return (
        <div className="h-screen flex items-center justify-center bg-gray-50">
            <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
        </div>
    );

    const inputCls =
        'mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500';

    return (
        <div className="min-h-screen bg-gray-50 font-sans text-gray-900 pb-10">
            <header className="bg-white p-4 shadow-sm flex items-center gap-4 sticky top-0 z-10">
                <button onClick={() => router.push('/villa')} className="text-gray-600">
                    <ArrowLeft />
                </button>
                <h1 className="text-lg font-bold text-gray-900">이용 정보 입력</h1>
            </header>

            <main className="p-4 space-y-4 max-w-lg mx-auto">
                {error && (
                    <div className="rounded-xl bg-rose-50 border border-rose-100 p-3 text-sm text-rose-700 flex items-start gap-2">
                        <span className="flex-1">{error}</span>
                        <button onClick={() => setError(null)}><X size={16} /></button>
                    </div>
                )}

                {info && (
                    <>
                        {/* 예약 요약 */}
                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100">
                            <div className="flex items-center justify-between">
                                <span className="font-bold text-gray-800">{info.facility_name}</span>
                                <span className="text-xs font-bold text-blue-700 bg-blue-100 px-2 py-1 rounded-full">
                                    확정
                                </span>
                            </div>
                            <p className="text-sm text-gray-600 mt-2">
                                {info.start_date} ~ {info.end_date} ({info.nights}박)
                            </p>
                            <p className="text-xs text-gray-400 mt-0.5">
                                {info.checkin_time} 입실 · {info.checkout_time} 퇴실 · 신청 인원 {info.participant_count}명
                            </p>
                            {(info.checkin_time_forced || info.checkout_time_forced) && (
                                <p className="text-[11px] text-amber-700 bg-amber-50 rounded-lg px-2 py-1.5 mt-2">
                                    앞뒤로 붙는 예약이 있어 {info.checkin_time_forced && info.checkout_time_forced
                                        ? '입실·퇴실 시간 모두'
                                        : info.checkin_time_forced ? '입실 시간이' : '퇴실 시간이'} 정규 시간으로 지정되었습니다. 위 시간을 반드시 지켜주세요.
                                </p>
                            )}
                        </section>

                        {saved && (
                            <div className={`rounded-xl p-3 text-sm flex items-start gap-2 ${
                                saved.warning
                                    ? 'bg-amber-50 text-amber-800 border border-amber-200'
                                    : 'bg-emerald-50 text-emerald-700 border border-emerald-100'
                            }`}>
                                {saved.warning ? <AlertTriangle size={18} className="shrink-0 mt-0.5" /> : <CheckCircle size={18} className="shrink-0 mt-0.5" />}
                                <span className="flex-1">
                                    {saved.warning ?? '저장되었습니다. 즐거운 이용 되세요.'}
                                    {saved.mailSent && <span className="block mt-1">{saved.mailSent}</span>}
                                </span>
                            </div>
                        )}

                        {/* 차량 정보 */}
                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100 space-y-3">
                            <h2 className="text-sm font-bold text-gray-800 flex items-center gap-2">
                                <Car size={16} className="text-blue-600" /> 차량 정보
                            </h2>

                            <label className="block">
                                <span className="text-xs font-bold text-gray-600">차량 대수</span>
                                <input
                                    type="number"
                                    min={0}
                                    max={MAX_VEHICLES}
                                    value={vehicleCount}
                                    onChange={e => setCount(Number(e.target.value))}
                                    className={inputCls}
                                />
                            </label>

                            {vehicleCount > 0 && (
                                <div className="space-y-2">
                                    <span className="text-xs font-bold text-gray-600">차량 번호</span>
                                    {Array.from({ length: vehicleCount }, (_, i) => (
                                        <input
                                            key={i}
                                            value={vehicleNumbers[i] ?? ''}
                                            onChange={e => setVehicleNumbers(prev => {
                                                const next = [...prev];
                                                next[i] = e.target.value;
                                                return next;
                                            })}
                                            placeholder={`${i + 1}번 차량 (예: 12가3456)`}
                                            className="w-full rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                                        />
                                    ))}
                                </div>
                            )}
                        </section>

                        {/* 이용 구성 */}
                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100 space-y-3">
                            <h2 className="text-sm font-bold text-gray-800 flex items-center gap-2">
                                <Users size={16} className="text-blue-600" /> 이용 구성
                            </h2>

                            <div className="grid grid-cols-2 gap-3">
                                <label className="block">
                                    <span className="text-xs font-bold text-gray-600">성인</span>
                                    <input
                                        type="number"
                                        min={0}
                                        value={adultCount}
                                        onChange={e => setAdultCount(Math.max(0, Number(e.target.value)))}
                                        className={inputCls}
                                    />
                                </label>
                                <label className="block">
                                    <span className="text-xs font-bold text-gray-600">아동 (15세 이하)</span>
                                    <input
                                        type="number"
                                        min={0}
                                        value={childCount}
                                        onChange={e => setChildCount(Math.max(0, Number(e.target.value)))}
                                        className={inputCls}
                                    />
                                </label>
                            </div>

                            <p className={`text-xs rounded-lg px-3 py-2 ${
                                mismatch ? 'bg-amber-50 text-amber-700' : 'bg-gray-50 text-gray-500'
                            }`}>
                                합계 {total}명 / 신청 인원 {info.participant_count}명
                                {mismatch && ' · 인원이 달라도 저장은 가능합니다. 변경이 필요하면 관리팀에 알려 주세요.'}
                            </p>
                        </section>

                        {/* 연락처 */}
                        <section className="rounded-2xl bg-white p-4 shadow-sm border border-gray-100 space-y-3">
                            <h2 className="text-sm font-bold text-gray-800 flex items-center gap-2">
                                <Phone size={16} className="text-blue-600" /> 이용자 연락처
                            </h2>
                            <label className="block">
                                <span className="text-xs font-bold text-gray-600">
                                    현장에서 연락 가능한 번호 <span className="text-rose-500">*</span>
                                </span>
                                <input
                                    type="tel"
                                    required
                                    value={contactPhone}
                                    onChange={e => setContactPhone(e.target.value)}
                                    placeholder="010-1234-5678"
                                    className={inputCls}
                                />
                            </label>
                            {contactPhoneMissing && (
                                <p className="text-xs text-rose-500">연락처는 필수 입력입니다.</p>
                            )}
                        </section>

                        <button
                            onClick={save}
                            disabled={saving || contactPhoneMissing}
                            className="w-full bg-blue-600 text-white font-bold py-3 rounded-xl hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                        >
                            {saving ? <Loader2 size={18} className="animate-spin" /> : '저장하기'}
                        </button>
                    </>
                )}
            </main>

            {/* 주차등록 요청 메일 — 관리실로 나가기 전에 내용을 확인·수정한다 */}
            {parkingMail && (
                <div className="fixed inset-0 z-50 bg-black/40 flex items-end sm:items-center justify-center sm:p-4">
                    <div className="bg-white w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl max-h-[92vh] overflow-y-auto">
                        <div className="sticky top-0 bg-white px-4 py-3 border-b border-gray-100 flex items-center gap-2">
                            <Mail size={18} className="text-blue-600" />
                            <h2 className="font-bold text-gray-900">주차등록 요청 메일</h2>
                            <button onClick={skipParkingMail} className="ml-auto text-gray-400">
                                <X size={18} />
                            </button>
                        </div>

                        <div className="p-4 space-y-3">
                            <p className="text-xs text-gray-600 bg-blue-50 rounded-lg px-3 py-2">
                                받는 곳 <span className="font-bold">{parkingMail.to}</span>
                                <span className="block mt-0.5 text-gray-500">
                                    내용을 확인하고 필요하면 수정한 뒤 발송해 주세요.
                                </span>
                            </p>

                            <label className="block">
                                <span className="text-xs font-bold text-gray-600">제목</span>
                                <input
                                    value={parkingMail.subject}
                                    onChange={e => setParkingMail(prev =>
                                        prev && { ...prev, subject: e.target.value })}
                                    className={inputCls}
                                />
                            </label>

                            <label className="block">
                                <span className="text-xs font-bold text-gray-600">내용</span>
                                <textarea
                                    rows={11}
                                    value={parkingMail.body}
                                    onChange={e => setParkingMail(prev =>
                                        prev && { ...prev, body: e.target.value })}
                                    className={`${inputCls} leading-relaxed`}
                                />
                            </label>

                            <div className="flex gap-2 pt-1">
                                <button
                                    onClick={skipParkingMail}
                                    disabled={sending}
                                    className="px-4 py-3 rounded-xl border border-gray-200 text-sm font-bold text-gray-600 disabled:opacity-50"
                                >
                                    발송 없이 닫기
                                </button>
                                <button
                                    onClick={sendParkingMail}
                                    disabled={sending || !parkingMail.subject.trim() || !parkingMail.body.trim()}
                                    className="flex-1 bg-blue-600 text-white font-bold py-3 rounded-xl hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                                >
                                    {sending
                                        ? <Loader2 size={18} className="animate-spin" />
                                        : <><Mail size={16} /> 발송하기</>}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
