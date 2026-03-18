'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { accessGym, accessGolf } from '@/lib/api';
import { Dumbbell, Flag, ArrowLeft, CheckCircle, XCircle, Loader2, AlertCircle } from 'lucide-react';
import Image from 'next/image';

export default function AccessPage() {
    const router = useRouter();
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ status: 'success' | 'error', message: string } | null>(null);
    const [showDisclaimer, setShowDisclaimer] = useState(false);
    const [pendingAction, setPendingAction] = useState<{ type: 'gym' | 'golf', mode: 'in' | 'out' } | null>(null);

    useEffect(() => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            router.replace('/login?redirect=/access');
        }
    }, [router]);

    const DISCLAIMER_TEXT = `[이용자 책임 원칙]\n\n본 시설은 임직원의 자율적인 판단하에 이용하는 공간입니다.\n시설 이용 중 이용자의 부주의, 신체 상태(지병 등), 안전 수칙 미준수로 인해\n발생하는 모든 사고 및 부상에 대하여 회사는 민·형사상의 책임을 지지 않습니다.\n\n이용 전 본인의 건강 상태를 반드시 고려해 주시기 바랍니다.`;

    const [doNotShow, setDoNotShow] = useState(false);

    const handleActionClick = (type: 'gym' | 'golf', mode: 'in' | 'out') => {
        if (mode === 'out') {
            executeAction(type, mode);
            return;
        }

        // Check for 7-day skip
        const hideUntil = localStorage.getItem('hideDisclaimerUntil');
        if (hideUntil && new Date().getTime() < parseInt(hideUntil)) {
            executeAction(type, mode);
            return;
        }

        setPendingAction({ type, mode });
        setShowDisclaimer(true);
    };

    const executeAction = async (type: 'gym' | 'golf', mode: 'in' | 'out') => {
        setLoading(true);
        try {
            let res;
            if (type === 'gym') {
                res = await accessGym();
            } else {
                res = await accessGolf();
            }
            setResult({ status: 'success', message: res.message });
        } catch (error: any) {
            setResult({ status: 'error', message: error.message || '처리 중 오류가 발생했습니다.' });
        } finally {
            setLoading(false);
            setPendingAction(null);
            setShowDisclaimer(false);
        }
    };

    const handleConfirm = async () => {
        if (!pendingAction) return;

        if (doNotShow) {
            const expiry = new Date().getTime() + 7 * 24 * 60 * 60 * 1000; // 7 days
            localStorage.setItem('hideDisclaimerUntil', expiry.toString());
        }

        executeAction(pendingAction.type, pendingAction.mode);
    };

    const closeWindow = () => {
        try {
            // Attempt to close for different browser environments
            window.open('', '_self')?.close();
            window.close();

            // For older IE/Edge
            const netscape = (window as any).netscape;
            if (netscape) {
                try {
                    netscape.security.PrivilegeManager.enablePrivilege("UniversalBrowserWrite");
                    window.open('', '_self');
                    window.close();
                } catch (e) { }
            }
        } catch (e) {
            console.error('Window close failed:', e);
        }

        // Fallback for mobile/webview if window.close fails
        setTimeout(() => {
            // Check if it's KakaoTalk in-app browser
            const userAgent = navigator.userAgent.toLowerCase();
            if (userAgent.indexOf("kakaotalk") > -1) {
                location.href = "kakaotalk://inappbrowser/close";
            } else {
                window.location.href = 'about:blank';
            }
        }, 300);
    };

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
            {/* Header */}
            <header className="bg-white p-4 shadow-sm flex items-center justify-center relative">
                <div className="flex items-center gap-2">
                    <Image src="/logo.svg" alt="BIT Wellness Center" width={120} height={40} />
                </div>
            </header>

            <main className="flex-1 flex flex-col p-6 gap-6 max-w-md mx-auto w-full justify-center">

                {result ? (
                    <div className="w-full bg-white rounded-3xl p-8 shadow-2xl text-center animate-fade-in relative overflow-hidden">
                        <div className={`w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-6 ${result.status === 'success' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'
                            }`}>
                            {result.status === 'success' ? <CheckCircle size={40} /> : <AlertCircle size={40} />}
                        </div>
                        <h2 className="text-2xl font-bold text-gray-900 mb-2">
                            {result.status === 'success' ? '완료되었습니다' : '오류 발생'}
                        </h2>
                        <p className="text-gray-500 mb-8 whitespace-pre-wrap">{result.message}</p>

                        {result.status === 'success' ? (
                            <button
                                onClick={closeWindow}
                                className="w-full py-4 bg-gray-900 text-white rounded-xl font-bold hover:bg-black transition-all shadow-lg"
                            >
                                화면 닫기
                            </button>
                        ) : (
                            <button
                                onClick={() => setResult(null)}
                                className="w-full py-4 bg-gray-200 text-gray-700 rounded-xl font-bold hover:bg-gray-300 transition-all"
                            >
                                다시 시도
                            </button>
                        )}
                        <p className="text-xs text-gray-400 mt-4">화면이 닫히지 않으면 브라우저를 종료해주세요.</p>
                    </div>
                ) : (
                    <>
                        <div className="text-center mb-4">
                            <h1 className="text-2xl font-bold text-gray-900">시설 입장/퇴실</h1>
                            <p className="text-gray-500 mt-2">이용하실 시설과 항목을 선택해주세요.</p>
                        </div>

                        {/* Gym Section */}
                        <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
                            <div className="flex items-center gap-3 mb-6">
                                <div className="p-2 bg-blue-100 text-blue-600 rounded-xl">
                                    <Dumbbell size={24} />
                                </div>
                                <h2 className="text-xl font-bold text-gray-800">헬스장</h2>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <button
                                    onClick={() => handleActionClick('gym', 'in')}
                                    className="py-4 bg-blue-50 text-blue-700 rounded-xl font-bold hover:bg-blue-600 hover:text-white transition-all shadow-sm border border-blue-100"
                                >
                                    입실
                                </button>
                                <button
                                    onClick={() => handleActionClick('gym', 'out')}
                                    className="py-4 bg-gray-50 text-gray-700 rounded-xl font-bold hover:bg-gray-200 transition-all shadow-sm border border-gray-200"
                                >
                                    퇴실
                                </button>
                            </div>
                        </div>

                        {/* Golf Section */}
                        <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
                            <div className="flex items-center gap-3 mb-6">
                                <div className="p-2 bg-emerald-100 text-emerald-600 rounded-xl">
                                    <Flag size={24} />
                                </div>
                                <h2 className="text-xl font-bold text-gray-800">스크린골프</h2>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <button
                                    onClick={() => handleActionClick('golf', 'in')}
                                    className="py-4 bg-emerald-50 text-emerald-700 rounded-xl font-bold hover:bg-emerald-600 hover:text-white transition-all shadow-sm border border-emerald-100"
                                >
                                    입실
                                </button>
                                <button
                                    onClick={() => handleActionClick('golf', 'out')}
                                    className="py-4 bg-gray-50 text-gray-700 rounded-xl font-bold hover:bg-gray-200 transition-all shadow-sm border border-gray-200"
                                >
                                    퇴실
                                </button>
                            </div>
                        </div>
                    </>
                )}

                {/* Loading Overlay */}
                {loading && (
                    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center">
                        <div className="bg-white p-6 rounded-2xl flex flex-col items-center gap-4 animate-bounce-in">
                            <Loader2 className="w-10 h-10 text-blue-600 animate-spin" />
                            <p className="font-bold text-gray-800">처리 중입니다...</p>
                        </div>
                    </div>
                )}

                {/* Disclaimer Modal */}
                {showDisclaimer && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-6 animate-fade-in">
                        <div className="w-full max-w-sm bg-white rounded-2xl p-6 shadow-2xl animate-scale-up">
                            <h3 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
                                <AlertCircle className="text-orange-500" /> 유의사항 확인
                            </h3>
                            <div className="bg-gray-50 p-4 rounded-xl border border-gray-200 text-sm text-gray-600 leading-relaxed whitespace-pre-line mb-4">
                                {DISCLAIMER_TEXT}
                            </div>

                            <label className="flex items-center gap-2 mb-6 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={doNotShow}
                                    onChange={(e) => setDoNotShow(e.target.checked)}
                                    className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                                <span className="text-sm text-gray-700 font-medium select-none">7일동안 보지 않기</span>
                            </label>

                            <div className="flex gap-3">
                                <button
                                    onClick={() => setShowDisclaimer(false)}
                                    className="flex-1 py-3 bg-gray-100 text-gray-600 rounded-xl font-bold hover:bg-gray-200 transition-colors"
                                >
                                    취소
                                </button>
                                <button
                                    onClick={handleConfirm}
                                    className="flex-1 py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-200"
                                >
                                    확인 ({pendingAction?.mode === 'in' ? '입실' : '퇴실'})
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </main>
            <footer className="p-6 text-center text-xs text-gray-400">
                © 2026 BIT Wellness Center. All rights reserved.
            </footer>
        </div>
    );
}
