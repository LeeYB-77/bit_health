'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { QRCodeSVG } from 'qrcode.react';
import { ArrowLeft, Copy, Check, Info } from 'lucide-react';

export default function AdminQRPage() {
    const router = useRouter();
    const [copiedLink, setCopiedLink] = useState<string | null>(null);
    const [baseUrl, setBaseUrl] = useState('');

    useEffect(() => {
        // Determine the base URL (e.g., http://59.10.164.2:3002)
        if (typeof window !== 'undefined') {
            setBaseUrl(window.location.origin);
        }
    }, []);

    const accessLink = `${baseUrl}/access`;

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text).then(() => {
            setCopiedLink('access');
            setTimeout(() => setCopiedLink(null), 2000);
        });
    };

    return (
        <div className="min-h-screen bg-gray-50 font-sans text-gray-900">
            {/* Header */}
            <div className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-10">
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => router.push('/admin')}
                            className="p-2 rounded-full hover:bg-gray-100 transition-colors text-gray-500"
                        >
                            <ArrowLeft size={20} />
                        </button>
                        <h1 className="text-xl font-bold text-gray-800">시설 입장 통합 QR 코드</h1>
                    </div>
                </div>
            </div>

            <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">

                <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 mb-8 flex items-start gap-3">
                    <Info className="text-blue-500 flex-shrink-0 mt-0.5" />
                    <div className="text-sm text-blue-800">
                        <p className="font-bold mb-1">안내</p>
                        <p>이 QR 코드는 <strong>통합 입실 시스템</strong>으로 연결됩니다. 사용자는 스캔 후 헬스장 또는 스크린골프 입실을 선택할 수 있습니다.</p>
                    </div>
                </div>

                <div className="flex justify-center">

                    {/* Unified QR Card */}
                    <div className="bg-white rounded-3xl shadow-lg border border-gray-100 p-10 flex flex-col items-center text-center max-w-md w-full">
                        <div className="mb-6 flex items-center gap-2">
                            <h2 className="text-2xl font-bold text-gray-900">BIT Health 입장</h2>
                        </div>

                        <p className="text-gray-500 mb-8 text-sm">스캔하여 헬스장/스크린골프 입실 체크</p>

                        <div className="bg-white p-4 rounded-2xl border-4 border-gray-100 mb-8 shadow-inner">
                            <QRCodeSVG value={accessLink} size={240} level="H" includeMargin />
                        </div>

                        <div className="w-full bg-gray-50 rounded-xl p-4 flex items-center justify-between gap-3 border border-gray-200">
                            <code className="text-xs text-gray-600 truncate flex-1 text-left">{accessLink}</code>
                            <button
                                onClick={() => copyToClipboard(accessLink)}
                                className="p-2 text-gray-500 hover:text-blue-600 transition-colors hover:bg-white rounded-lg"
                                title="링크 복사"
                            >
                                {copiedLink === 'access' ? <Check size={18} className="text-green-600" /> : <Copy size={18} />}
                            </button>
                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
}
