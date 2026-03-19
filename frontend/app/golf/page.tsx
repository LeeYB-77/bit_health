'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { getGolfSlots, reserveGolf, getMyReservations, accessGolf, cancelGolfReservation, GolfSlot, Reservation } from '@/lib/api';
import { Calendar, Clock, Users, X, ArrowLeft, Plus, QrCode, Trash2 } from 'lucide-react';

function GolfContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const [date, setDate] = useState<string>('');
    const [slots, setSlots] = useState<GolfSlot[]>([]);
    const [myReservations, setMyReservations] = useState<Reservation[]>([]);
    const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
    const [participants, setParticipants] = useState(1);
    const [companions, setCompanions] = useState('');
    const [loading, setLoading] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [accessModalOpen, setAccessModalOpen] = useState(false);
    const [accessResult, setAccessResult] = useState('');

    useEffect(() => {
        const today = new Date().toISOString().split('T')[0];
        setDate(today);
        fetchMyReservations();

        // Check for QR access action
        if (searchParams.get('action') === 'access') {
            setAccessModalOpen(true);
        }
    }, [searchParams]);

    useEffect(() => {
        if (date) {
            fetchSlots(date);
        }
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

        // Validation for companions
        if (participants > 1 && !companions.trim()) {
            alert('2인 이상 예약 시 동반자 정보를 입력해야 합니다.');
            return;
        }

        setLoading(true);
        try {
            const currentSlotIndex = slots.findIndex(s => s.time === selectedSlot);
            if (currentSlotIndex === -1) throw new Error("Invalid slot");

            const startTime = `${date}T${slots[currentSlotIndex].time}:00`;

            // Calculate end time based on the last slot used
            // If participants = 1, use current slot end time
            // If participants > 1, use the end time of the (participants-1)-th next slot
            const lastSlotIndex = currentSlotIndex + participants - 1;
            const lastSlot = slots[lastSlotIndex]; // We validated existence in + button logic

            const endTime = `${date}T${lastSlot.end_time}:00`;

            await reserveGolf({
                start_time: startTime,
                end_time: endTime,
                participant_count: participants,
                companions: companions
            });

            alert('예약이 완료되었습니다.');
            setModalOpen(false);
            setParticipants(1); // Reset
            setCompanions('');
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
                router.replace('/golf'); // Clear query param
            }, 2000);
        } catch (error: any) {
            setAccessResult('오류가 발생했습니다.');
        } finally {
            setLoading(false);
        }
    };

    // Helper to extract hour from HH:MM
    const getHour = (timeStr: string) => parseInt(timeStr.split(':')[0]);

    return (
        <div className="min-h-screen bg-gray-50 pb-20 font-sans">
            <header className="bg-white p-4 shadow-sm flex items-center gap-4 sticky top-0 z-10">
                <button onClick={() => router.push('/')} className="text-gray-600">
                    <ArrowLeft />
                </button>
                <h1 className="text-lg font-bold text-gray-900">스크린골프 예약</h1>
            </header>

            <main className="p-4 space-y-6 max-w-lg mx-auto">
                {/* Date Picker */}
                <div className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100">
                    <label className="block text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
                        <Calendar size={18} className="text-blue-600" /> 날짜 선택
                    </label>
                    <input
                        type="date"
                        value={date}
                        onChange={(e) => setDate(e.target.value)}
                        className="w-full rounded-xl border border-gray-200 bg-gray-50 p-3 text-sm focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                    />
                </div>

                {/* Slots */}
                <div className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100">
                    <h2 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
                        <Clock size={18} className="text-blue-600" /> 시간 선택
                    </h2>
                    <div className="grid grid-cols-2 gap-3">
                        {slots.length > 0 ? slots.map((slot) => (
                            <button
                                key={slot.time}
                                disabled={!slot.available}
                                onClick={() => {
                                    setSelectedSlot(slot.time);
                                    setModalOpen(true);
                                }}
                                className={`flex flex-col items-center justify-center rounded-xl p-3 text-sm font-medium transition-all ${!slot.available
                                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed border border-transparent'
                                    : 'bg-white border border-blue-100 text-blue-600 hover:bg-blue-50 hover:border-blue-300 shadow-sm'
                                    }`}
                            >
                                <span className="text-base font-bold">{slot.time} ~ {slot.end_time}</span>
                                <span className={`text-[10px] mt-1 px-1.5 py-0.5 rounded-full ${slot.available ? 'bg-blue-100 text-blue-600' : 'bg-gray-200 text-gray-500'}`}>
                                    {slot.available ? '예약가능' : '마감'}
                                </span>
                            </button>
                        )) : (
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
                            {myReservations.map(res => (
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
                                        <p className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded w-fit">
                                            인원: {res.participant_count}명 {res.companions && `(동반: ${res.companions})`}
                                        </p>
                                    </div>
                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => handleCancel(res.id)}
                                            className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                                        >
                                            <Trash2 size={18} />
                                        </button>
                                        <div className={`text-xs px-3 py-1.5 rounded-full font-medium h-fit ${res.status === 'reserved' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                                            }`}>
                                            {res.status === 'reserved' ? '예약됨' : res.status}
                                        </div>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            </main>

            {/* Reservation Modal */}
            {modalOpen && (
                <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
                    <div className="w-full max-w-sm rounded-3xl bg-white p-6 shadow-2xl animate-slide-up sm:animate-none">
                        <div className="flex justify-between items-center mb-6">
                            <div className="flex flex-col">
                                <span className="text-sm text-gray-500">예약 일시</span>
                                <h3 className="text-xl font-bold text-gray-900">{date} {selectedSlot}</h3>
                            </div>
                            <button onClick={() => setModalOpen(false)} className="p-2 bg-gray-100 rounded-full hover:bg-gray-200 transition-colors">
                                <X className="w-5 h-5 text-gray-600" />
                            </button>
                        </div>

                        <div className="space-y-6">
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

                                            if (newCount > 4) {
                                                alert("최대 4명까지 예약 가능합니다.");
                                                return;
                                            }

                                            // Validate by Slot Index
                                            if (selectedSlot) {
                                                const currentIndex = slots.findIndex(s => s.time === selectedSlot);
                                                if (currentIndex === -1) return;

                                                // We need to check 'newCount' number of consecutive slots
                                                // 1 person = index [i]
                                                // 2 people = index [i], [i+1]
                                                // ...
                                                let isAvailable = true;

                                                for (let i = 0; i < newCount; i++) {
                                                    const targetIndex = currentIndex + i;

                                                    // 1. Check if slot exists
                                                    if (targetIndex >= slots.length) {
                                                        isAvailable = false;
                                                        break;
                                                    }

                                                    const targetSlot = slots[targetIndex];

                                                    // 2. Check if slot is available
                                                    if (!targetSlot.available) {
                                                        isAvailable = false;
                                                        break;
                                                    }

                                                    // 3. Check continuity (if not the first slot)
                                                    if (i > 0) {
                                                        const prevSlot = slots[targetIndex - 1];
                                                        // "prev.End" must equal "curr.Start"
                                                        // Need to compare strictly? Or just assume array is sorted?
                                                        // Let's compare strings: "19:10" vs "19:10"
                                                        // Note: end_time might be "20:09" and start time "20:10" -> 1 min gap? 
                                                        // Usually end_time in UI is exclusive or inclusive?
                                                        // In backend/golf.py:
                                                        // weekday: 10:00 -> 12:00. Next is 14:00. GAP.
                                                        // weekend: 14:00 -> 15:00. Next 15:00. CONTINUOUS.

                                                        // We interpret "continuous" as:
                                                        // The minute difference between PrevEnd and CurrStart should be small (<= 1 min used for :59/:00 boundary?)
                                                        // Or simplest: Just rely on available slots in the array being sufficient?
                                                        // NO, because of lunch break gaps.

                                                        // Improved continuity check:
                                                        // Convert HH:MM to minutes.
                                                        const [ph, pm] = prevSlot.end_time.split(':').map(Number);
                                                        const [ch, cm] = targetSlot.time.split(':').map(Number);

                                                        const pMinutes = ph * 60 + pm;
                                                        const cMinutes = ch * 60 + cm;

                                                        // Allow max 1 minute gap (e.g. 20:09 -> 20:10)
                                                        if (cMinutes - pMinutes > 1) {
                                                            isAvailable = false;
                                                            break;
                                                        }
                                                    }
                                                }

                                                if (!isAvailable) {
                                                    alert("이후 시간에 예약이 있거나 연속된 시간이 아니어서 인원을 늘릴 수 없습니다.");
                                                    return;
                                                }
                                            }
                                            setParticipants(newCount);
                                        }}
                                        className="w-10 h-10 flex items-center justify-center bg-white rounded-lg shadow-sm text-gray-600 border border-gray-100 hover:bg-gray-50 active:scale-95 transition-all"
                                    >+</button>
                                </div>
                                <p className="text-xs text-blue-600 mt-2">* 1인당 1시간씩 자동 배정됩니다.</p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    동반자 정보 {participants > 1 ? <span className="text-red-500">(필수)</span> : <span className="text-gray-400">(선택)</span>}
                                </label>
                                <input
                                    type="text"
                                    placeholder={participants > 1 ? "동반자 이름, 부서 등을 입력해주세요" : "이름, 부서 등 입력 (선택)"}
                                    value={companions}
                                    onChange={(e) => setCompanions(e.target.value)}
                                    className={`w-full rounded-xl border p-3 text-sm text-gray-900 focus:ring-2 outline-none transition-all ${participants > 1 && !companions.trim() ? 'border-red-300 focus:ring-red-200 bg-red-50' : 'border-gray-200 bg-gray-50 focus:ring-blue-500'
                                        }`}
                                    onKeyPress={(e) => e.key === 'Enter' && handleReserve()}
                                />
                                {participants > 1 && !companions.trim() && (
                                    <p className="text-xs text-red-500 mt-1">2인 이상 예약 시 동반자 정보는 필수입니다.</p>
                                )}
                            </div>

                            <button
                                onClick={handleReserve}
                                disabled={loading}
                                className="w-full bg-blue-600 text-white py-4 rounded-xl font-bold text-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed shadow-lg shadow-blue-200 transition-all active:scale-[0.98]"
                            >
                                {loading ? '처리 중...' : `${participants}시간 예약 확정하기`}
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
                                        onClick={() => {
                                            setAccessModalOpen(false);
                                            router.replace('/golf');
                                        }}
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
