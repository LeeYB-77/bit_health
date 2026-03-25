'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { getGolfSlots, reserveGolf, getMyReservations, accessGolf, cancelGolfReservation, GolfSlot, Reservation } from '@/lib/api';
import { Calendar, Clock, Users, X, ArrowLeft, QrCode, Trash2, ChevronDown, ChevronUp, Info } from 'lucide-react';

// 우선순위 설정
const PRIORITIES = [
    {
        value: 1,
        label: '최우선',
        sub: '비트직원들과 함께',
        color: 'border-red-400 bg-red-50 text-red-700',
        activeColor: 'border-red-500 bg-red-100 text-red-900 ring-2 ring-red-400 font-bold',
        badge: 'bg-red-100 text-red-600',
        badgeLabel: '🔴 최우선',
        desc: '비트 직원들끼리 이용합니다. 타인이 이 슬롯을 교체할 수 없습니다.',
    },
    {
        value: 2,
        label: '우선',
        sub: '직원과 동반한 고객',
        color: 'border-amber-400 bg-amber-50 text-amber-700',
        activeColor: 'border-amber-500 bg-amber-100 text-amber-900 ring-2 ring-amber-400 font-bold',
        badge: 'bg-amber-100 text-amber-700',
        badgeLabel: '🟡 우선',
        desc: '직원과 고객이 함께 이용합니다. 「양보」예약 슬롯을 교체할 수 있으며, 「최우선」에게 양보해야 합니다.',
    },
    {
        value: 3,
        label: '양보',
        sub: '직원과 동반한 가족',
        color: 'border-green-400 bg-green-50 text-green-700',
        activeColor: 'border-green-500 bg-green-100 text-green-900 ring-2 ring-green-400 font-bold',
        badge: 'bg-green-100 text-green-700',
        badgeLabel: '🟢 양보',
        desc: '직원과 가족이 이용합니다. 「최우선」·「우선」 예약자에게 슬롯을 내어줄 수 있습니다.',
    },
];

const getPriority = (v: number) => PRIORITIES.find(p => p.value === v) ?? PRIORITIES[2];

function GolfContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const [date, setDate] = useState<string>('');
    const [slots, setSlots] = useState<GolfSlot[]>([]);
    const [myReservations, setMyReservations] = useState<Reservation[]>([]);
    const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
    const [participants, setParticipants] = useState(1);
    const [companions, setCompanions] = useState('');
    const [priority, setPriority] = useState<number>(1); // 기본: 최우선
    const [loading, setLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [accessModalOpen, setAccessModalOpen] = useState(false);
    const [accessResult, setAccessResult] = useState('');
    const [ruleOpen, setRuleOpen] = useState(false);

    // 현재 선택된 슬롯 객체
    const currentSlotObj = slots.find(s => s.time === selectedSlot);
    const isPreempting = currentSlotObj && !currentSlotObj.available && currentSlotObj.can_preempt;

    useEffect(() => {
        const now = new Date();
        const offset = now.getTimezoneOffset() * 60000;
        const today = new Date(now.getTime() - offset).toISOString().split('T')[0];
        setDate(today);
        fetchMyReservations();
        if (searchParams.get('action') === 'access') {
            setAccessModalOpen(true);
        }
    }, [searchParams]);

    useEffect(() => {
        if (date) fetchSlots(date);
    }, [date]);

    const fetchSlots = async (selectedDate: string) => {
        try {
            const data = await getGolfSlots(selectedDate);
            setSlots(data);
        } catch (error) {
            console.error('Failed to fetch slots', error);
        }
    };

    const fetchMyReservations = async () => {
        try {
            const data = await getMyReservations();
            setMyReservations(data);
        } catch (error) {
            console.error('Failed to fetch reservations', error);
        }
    };

    const handleReserve = async () => {
        if (!selectedSlot || !date) return;

        // 2인 이상 동반자 필수 검증 (프론트엔드)
        if (participants > 1 && !companions.trim()) {
            alert('2인 이상 예약 시 동반자 정보를 입력해야 합니다.');
            return;
        }

        if (!confirm(
            isPreempting
                ? `⚠️ 기존 예약자의 슬롯(${getPriority(currentSlotObj!.taken_by_priority!).label})을 교체합니다.\n예약을 진행하시겠습니까?`
                : '예약을 확정하시겠습니까?'
        )) return;

        setLoading(true);
        try {
            const currentSlotIndex = slots.findIndex(s => s.time === selectedSlot);
            if (currentSlotIndex === -1) throw new Error("Invalid slot");

            const startTime = `${date}T${slots[currentSlotIndex].time}:00`;
            const lastSlotIndex = currentSlotIndex + participants - 1;
            const lastSlot = slots[lastSlotIndex];
            const endTime = `${date}T${lastSlot.end_time}:00`;

            await reserveGolf({
                start_time: startTime,
                end_time: endTime,
                participant_count: participants,
                companions: companions || null,
                priority: priority,
            });

            alert('예약이 완료되었습니다.');
            setModalOpen(false);
            setParticipants(1);
            setCompanions('');
            setPriority(1);
            fetchSlots(date);
            fetchMyReservations();
        } catch (error: any) {
            alert(error.message || '예약 실패');
        } finally {
            setLoading(false);
        }
    };

    const handleCancel = async (id: number) => {
        if (!confirm('정말 예약을 취소하시겠습니까?')) return;
        try {
            await cancelGolfReservation(id);
            alert('예약이 취소되었습니다.');
            fetchSlots(date);
            fetchMyReservations();
        } catch (error: any) {
            alert(error.message || '취소 실패');
        }
    };

    const handleAccess = async () => {
        setLoading(true);
        try {
            const res = await accessGolf();
            setAccessResult(res.message);
            setTimeout(() => {
                setAccessModalOpen(false);
                setAccessResult('');
                router.replace('/golf');
            }, 2000);
        } catch {
            setAccessResult('오류가 발생했습니다.');
        } finally {
            setLoading(false);
        }
    };

    const openModal = (slotTime: string) => {
        const slot = slots.find(s => s.time === slotTime);
        if (!slot) return;
        // 교체 불가 슬롯 (available=false이고 can_preempt=false)은 클릭 불가
        if (!slot.available && !slot.can_preempt) return;
        setSelectedSlot(slotTime);
        setModalOpen(true);
    };

    const selectedPriority = PRIORITIES.find(p => p.value === priority) ?? PRIORITIES[0];

    return (
        <div className="min-h-screen bg-gray-50 pb-20 font-sans">
            <header className="bg-white p-4 shadow-sm flex items-center gap-4 sticky top-0 z-10">
                <button onClick={() => router.push('/')} className="text-gray-600">
                    <ArrowLeft />
                </button>
                <h1 className="text-lg font-bold text-gray-900">스크린골프 예약</h1>
            </header>

            <main className="p-4 space-y-6 max-w-lg mx-auto">
                {/* 우선순위 규칙 안내 */}
                <div className="rounded-2xl bg-blue-50 border border-blue-100 overflow-hidden">
                    <button
                        className="w-full flex items-center justify-between p-4 text-sm font-bold text-blue-700"
                        onClick={() => setRuleOpen(v => !v)}
                    >
                        <span className="flex items-center gap-2"><Info size={16} /> 예약 우선순위 규칙 안내</span>
                        {ruleOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </button>
                    {ruleOpen && (
                        <div className="px-4 pb-4 text-xs text-blue-800 space-y-1 leading-relaxed">
                            <p>🔴 <b>최우선</b> (비트직원끼리): 타인이 교체 불가</p>
                            <p>🟡 <b>우선</b> (직원+고객): 「양보」슬롯만 교체 가능 / 「최우선」에게 양보</p>
                            <p>🟢 <b>양보</b> (직원+가족): 「최우선」·「우선」에게 양보</p>
                            <hr className="border-blue-200 my-2" />
                            <p>• 타인 교체는 <b>시작 3시간 전까지</b>만 가능</p>
                            <p>• 본인 취소는 <b>언제든지</b> 가능</p>
                            <p>• 예약 후 <b>미사용 시 1개월 예약 불가</b></p>
                        </div>
                    )}
                </div>

                {/* Date Picker */}
                <div className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100">
                    <label className="block text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
                        <Calendar size={18} className="text-blue-600" /> 날짜 선택
                    </label>
                    <input
                        type="date"
                        value={date}
                        onChange={(e) => setDate(e.target.value)}
                        className="w-full rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm text-gray-900 focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                    />
                </div>

                {/* Slots */}
                <div className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100">
                    <h2 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
                        <Clock size={18} className="text-blue-600" /> 시간 선택
                    </h2>
                    <div className="grid grid-cols-2 gap-3">
                        {slots.length > 0 ? slots.map((slot) => {
                            const pInfo = slot.taken_by_priority ? getPriority(slot.taken_by_priority) : null;
                            const isDisabled = !slot.available && !slot.can_preempt;
                            const isPreemptable = !slot.available && slot.can_preempt;

                            return (
                                <button
                                    key={slot.time}
                                    disabled={isDisabled}
                                    onClick={() => openModal(slot.time)}
                                    className={`flex flex-col items-center justify-center rounded-xl p-3 text-sm font-medium transition-all relative ${
                                        isDisabled
                                            ? 'bg-gray-100 text-gray-400 cursor-not-allowed border border-transparent'
                                            : isPreemptable
                                                ? 'bg-orange-50 border border-orange-300 text-orange-700 hover:bg-orange-100 shadow-sm'
                                                : 'bg-white border border-blue-100 text-blue-600 hover:bg-blue-50 hover:border-blue-300 shadow-sm'
                                    }`}
                                >
                                    <span className="text-base font-bold">{slot.time} ~ {slot.end_time}</span>
                                    {slot.available ? (
                                        <span className="text-[10px] mt-1 px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-600">예약가능</span>
                                    ) : isPreemptable ? (
                                        <div className="flex flex-col items-center gap-0.5 mt-1">
                                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${pInfo?.badge}`}>{pInfo?.badgeLabel}</span>
                                            <span className="text-[9px] text-orange-500 font-bold">교체 가능</span>
                                        </div>
                                    ) : (
                                        <span className={`text-[10px] mt-1 px-1.5 py-0.5 rounded-full ${pInfo?.badge ?? 'bg-gray-200 text-gray-500'}`}>
                                            {pInfo?.badgeLabel ?? '마감'}
                                        </span>
                                    )}
                                </button>
                            );
                        }) : (
                            <div className="col-span-2 text-center py-8 text-gray-400">
                                예약 가능한 시간이 없습니다.
                            </div>
                        )}
                    </div>
                </div>

                {/* My Reservations */}
                <div className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100">
                    <h2 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
                        <Users size={18} className="text-blue-600" /> 내 예약 현황
                    </h2>
                    {myReservations.length === 0 ? (
                        <div className="text-center py-8 text-gray-400 bg-gray-50 rounded-xl border border-gray-100 border-dashed">
                            예약 내역이 없습니다.
                        </div>
                    ) : (
                        <ul className="space-y-3">
                            {myReservations.map(res => {
                                const pInfo = getPriority(res.priority ?? 3);
                                return (
                                    <li key={res.id} className="border border-gray-100 bg-white rounded-xl p-4 flex justify-between items-center shadow-sm">
                                        <div>
                                            <div className="flex items-center gap-2 mb-1">
                                                <span className="font-bold text-gray-800 text-lg">
                                                    {new Date(res.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                </span>
                                                <span className="text-xs text-gray-500">
                                                    {new Date(res.start_time).toLocaleDateString()}
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <p className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded w-fit">
                                                    인원: {res.participant_count}명 {res.companions && `(동반: ${res.companions})`}
                                                </p>
                                                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${pInfo.badge}`}>
                                                    {pInfo.badgeLabel}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="flex gap-2 items-center">
                                            <button
                                                onClick={() => handleCancel(res.id)}
                                                className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                            <div className={`text-xs px-3 py-1.5 rounded-full font-medium h-fit ${
                                                res.status === 'reserved' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                                            }`}>
                                                {res.status === 'reserved' ? '예약됨' 
                                                 : res.status === 'canceled' ? '취소됨'
                                                 : res.status === 'no_show' ? '미사용'
                                                 : res.status === 'completed' ? '사용 완료'
                                                 : res.status}
                                            </div>
                                        </div>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
            </main>

            {/* Reservation Modal */}
            {modalOpen && (
                <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <div className="w-full max-w-sm rounded-3xl bg-white p-6 shadow-2xl">
                        {/* 헤더 */}
                        <div className="flex justify-between items-center mb-4">
                            <div className="flex flex-col">
                                <span className="text-sm text-gray-500">예약 일시</span>
                                <h3 className="text-xl font-bold text-gray-900">{date} {selectedSlot}</h3>
                            </div>
                            <button onClick={() => setModalOpen(false)} className="p-2 bg-gray-100 rounded-full hover:bg-gray-200 transition-colors">
                                <X className="w-5 h-5 text-gray-600" />
                            </button>
                        </div>

                        {/* 교체 알림 배너 */}
                        {isPreempting && (
                            <div className="mb-4 p-3 bg-orange-50 border border-orange-200 rounded-xl text-xs text-orange-700">
                                ⚠️ 이 슬롯은 현재 <b>{getPriority(currentSlotObj!.taken_by_priority!).label}</b> 등급으로 예약되어 있습니다.<br />
                                더 높은 우선순위로 예약하면 기존 예약이 취소됩니다.
                            </div>
                        )}

                        <div className="space-y-5">
                            {/* 우선순위 선택 */}
                            <div>
                                <label className="block text-sm font-bold text-gray-700 mb-2">예약 우선순위 선택</label>
                                <div className="space-y-2">
                                    {PRIORITIES.map(p => (
                                        <button
                                            key={p.value}
                                            onClick={() => setPriority(p.value)}
                                            className={`w-full text-left rounded-xl border-2 px-4 py-3 transition-all ${priority === p.value ? p.activeColor : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'}`}
                                        >
                                            <div className="flex items-center gap-2">
                                                <span className="text-base">{p.badgeLabel}</span>
                                                <span className="text-sm font-medium">{p.sub}</span>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                                {/* 선택된 우선순위 안내 */}
                                <div className={`mt-2 p-3 rounded-xl text-xs leading-relaxed ${selectedPriority.color} border`}>
                                    ℹ️ {selectedPriority.desc}
                                </div>
                            </div>

                            {/* 인원 수 */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">참여 인원 (인원수 = 이용 시간)</label>
                                <div className="flex items-center justify-between bg-gray-50 p-2 rounded-xl border border-gray-200">
                                    <button
                                        onClick={() => setParticipants(Math.max(1, participants - 1))}
                                        className="w-10 h-10 flex items-center justify-center bg-white rounded-lg shadow-sm text-gray-600 border border-gray-100 hover:bg-gray-50 active:scale-95 transition-all"
                                    >-</button>
                                    <span className="font-bold text-lg text-gray-800">{participants}명 ({participants}시간)</span>
                                    <button
                                        onClick={() => {
                                            const newCount = participants + 1;
                                            if (newCount > 4) { alert("최대 4명까지 예약 가능합니다."); return; }
                                            if (selectedSlot) {
                                                const currentIndex = slots.findIndex(s => s.time === selectedSlot);
                                                if (currentIndex === -1) return;
                                                let isAvailable = true;
                                                for (let i = 0; i < newCount; i++) {
                                                    const targetIndex = currentIndex + i;
                                                    if (targetIndex >= slots.length) { isAvailable = false; break; }
                                                    const targetSlot = slots[targetIndex];
                                                    if (!targetSlot.available && !targetSlot.can_preempt) { isAvailable = false; break; }
                                                    if (i > 0) {
                                                        const prevSlot = slots[targetIndex - 1];
                                                        const [ph, pm] = prevSlot.end_time.split(':').map(Number);
                                                        const [ch, cm] = targetSlot.time.split(':').map(Number);
                                                        if ((ch * 60 + cm) - (ph * 60 + pm) > 1) { isAvailable = false; break; }
                                                    }
                                                }
                                                if (!isAvailable) { alert("이후 시간에 예약이 있거나 연속된 시간이 아닙니다."); return; }
                                            }
                                            setParticipants(newCount);
                                        }}
                                        className="w-10 h-10 flex items-center justify-center bg-white rounded-lg shadow-sm text-gray-600 border border-gray-100 hover:bg-gray-50 active:scale-95 transition-all"
                                    >+</button>
                                </div>
                                <p className="text-xs text-blue-600 mt-1">* 1인당 1시간씩 자동 배정됩니다.</p>
                            </div>

                            {/* 동반자 정보 */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    동반자 정보{' '}
                                    {participants > 1
                                        ? <span className="text-red-500">(필수)</span>
                                        : <span className="text-gray-400">(선택)</span>
                                    }
                                </label>
                                <input
                                    type="text"
                                    placeholder={participants > 1 ? "동반자 이름, 부서 등을 입력해주세요 (필수)" : "이름, 부서 등 입력 (선택)"}
                                    value={companions}
                                    onChange={(e) => setCompanions(e.target.value)}
                                    className={`w-full rounded-xl border p-3 text-sm text-gray-900 focus:ring-2 outline-none transition-all ${
                                        participants > 1 && !companions.trim()
                                            ? 'border-red-300 focus:ring-red-200 bg-red-50'
                                            : 'border-gray-200 bg-gray-50 focus:ring-blue-500'
                                    }`}
                                    onKeyPress={(e) => e.key === 'Enter' && handleReserve()}
                                />
                                {participants > 1 && !companions.trim() && (
                                    <p className="text-xs text-red-500 mt-1">2인 이상 예약 시 동반자 정보는 필수입니다.</p>
                                )}
                            </div>

                            <button
                                onClick={handleReserve}
                                disabled={loading || (participants > 1 && !companions.trim())}
                                className="w-full bg-blue-600 text-white py-4 rounded-xl font-bold text-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed shadow-lg shadow-blue-200 transition-all active:scale-[0.98]"
                            >
                                {loading ? '처리 중...' : isPreempting ? `⚠️ 교체 후 ${participants}시간 예약` : `${participants}시간 예약 확정하기`}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Access Modal (QR Scan) */}
            {accessModalOpen && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-md p-6">
                    <div className="w-full max-w-sm rounded-3xl bg-white p-8 shadow-2xl text-center">
                        <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-6">
                            <QrCode className="w-8 h-8 text-blue-600" />
                        </div>
                        <h2 className="text-2xl font-bold text-gray-900 mb-2">스크린골프 입장/퇴실</h2>

                        {!accessResult ? (
                            <>
                                <p className="text-gray-500 mb-8 leading-relaxed">
                                    QR 코드가 인식되었습니다.<br />
                                    입실 또는 퇴실 처리를 진행하시겠습니까?
                                </p>
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => { setAccessModalOpen(false); router.replace('/golf'); }}
                                        className="flex-1 py-3 px-4 rounded-xl border border-gray-200 text-gray-600 font-medium hover:bg-gray-50 transition-colors"
                                    >
                                        취소
                                    </button>
                                    <button
                                        onClick={handleAccess}
                                        disabled={loading}
                                        className="flex-1 py-3 px-4 rounded-xl bg-blue-600 text-white font-bold hover:bg-blue-700 shadow-lg shadow-blue-200 transition-all active:scale-95"
                                    >
                                        {loading ? '처리 중...' : '확인'}
                                    </button>
                                </div>
                            </>
                        ) : (
                            <div className="py-4">
                                <p className="text-xl font-bold text-blue-600 mb-2">{accessResult}</p>
                                <p className="text-gray-400 text-sm">잠시 후 화면이 닫힙니다...</p>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default function GolfPage() {
    return (
        <Suspense fallback={<div className="min-h-screen flex items-center justify-center text-gray-500">Loading...</div>}>
            <GolfContent />
        </Suspense>
    );
}
