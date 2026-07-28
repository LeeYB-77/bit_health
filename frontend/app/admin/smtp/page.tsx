'use client';
// 메일(SMTP) 발송 계정 설정 화면. 비밀번호는 서버에서 암호화 저장되며 조회 시 마스킹된다.

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { API_URL } from '@/lib/api';
import { AlertTriangle, ArrowLeft, Loader2, Mail, Save, Send, X } from 'lucide-react';

interface SmtpSettings {
    host: string;
    port: number;
    use_tls: boolean;
    username: string;
    from_name: string;
    from_email: string;
    password_set: boolean;      // 저장된 비밀번호 존재 여부. 값 자체는 내려오지 않는다.
    encryption_available: boolean;
    configured: boolean;
}

const authHeaders = (): HeadersInit => ({
    'Content-Type': 'application/json',
    Authorization: `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('access_token') : ''}`,
});

async function call(path: string, method: 'GET' | 'POST' = 'GET', body?: unknown) {
    const res = await fetch(`${API_URL}${path}`, {
        method,
        headers: authHeaders(),
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || '요청에 실패했습니다.');
    return data;
}

export default function AdminSmtpPage() {
    const router = useRouter();
    const [form, setForm] = useState<SmtpSettings | null>(null);
    // 새로 입력한 비밀번호만 담는다. 비어 있으면 기존 값을 그대로 둔다.
    const [newPassword, setNewPassword] = useState('');
    const [testEmail, setTestEmail] = useState('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [message, setMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

    const load = useCallback(async () => {
        try {
            setForm(await call('/api/admin/smtp'));
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '불러오지 못했습니다.' });
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const set = <K extends keyof SmtpSettings>(key: K, value: SmtpSettings[K]) =>
        setForm(f => (f ? { ...f, [key]: value } : f));

    const save = async () => {
        if (!form) return;
        setSaving(true);
        setMessage(null);
        try {
            const body = await call('/api/admin/smtp', 'POST', {
                host: form.host,
                port: Number(form.port),
                use_tls: form.use_tls,
                username: form.username,
                from_name: form.from_name,
                from_email: form.from_email,
                // 비워두면 password를 아예 보내지 않아 서버가 기존 비밀번호를 유지한다
                ...(newPassword ? { password: newPassword } : {}),
            });
            setMessage({ type: 'ok', text: body.message });
            setNewPassword('');
            await load();
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '저장에 실패했습니다.' });
        } finally {
            setSaving(false);
        }
    };

    const sendTest = async () => {
        if (!testEmail.trim()) return;
        setTesting(true);
        setMessage(null);
        try {
            const body = await call('/api/admin/smtp/test', 'POST', { to_email: testEmail.trim() });
            setMessage({ type: 'ok', text: body.message });
        } catch (e) {
            setMessage({ type: 'err', text: e instanceof Error ? e.message : '발송에 실패했습니다.' });
        } finally {
            setTesting(false);
        }
    };

    if (loading) return <div className="p-8 text-center text-gray-500">불러오는 중...</div>;
    if (!form) return <div className="p-8 text-center text-rose-500">설정을 불러올 수 없습니다.</div>;

    const inputCls =
        'mt-1 w-full rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500';

    return (
        <div className="space-y-6 px-4 sm:px-0 max-w-2xl">
            <div className="flex items-center gap-2">
                <button
                    onClick={() => router.push('/admin')}
                    className="p-2 -ml-2 rounded-full hover:bg-gray-100 transition-colors text-gray-500"
                >
                    <ArrowLeft size={20} />
                </button>
                <Mail size={22} className="text-blue-600" />
                <h2 className="text-xl font-bold text-gray-900">메일(SMTP) 설정</h2>
                {form.configured && (
                    <span className="text-xs font-bold text-emerald-700 bg-emerald-100 px-2 py-1 rounded-full">
                        설정됨
                    </span>
                )}
            </div>

            <p className="text-sm text-gray-500">
                비트별장 예약 확정 안내를 보낼 발신 계정입니다. 비밀번호는 서버에서 암호화되어 저장되며
                화면에는 다시 표시되지 않습니다.
            </p>

            {!form.encryption_available && (
                <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800 flex items-start gap-2">
                    <AlertTriangle size={18} className="shrink-0 mt-0.5" />
                    <div>
                        <p className="font-bold">암호화 키가 설정되지 않았습니다.</p>
                        <p className="mt-1 text-xs leading-relaxed">
                            서버 <code className="bg-amber-100 px-1 rounded">.env</code>에{' '}
                            <code className="bg-amber-100 px-1 rounded">SETTINGS_ENCRYPTION_KEY</code>를 추가한 뒤
                            재배포해야 비밀번호를 저장할 수 있습니다. 다른 기능은 정상 동작합니다.
                        </p>
                    </div>
                </div>
            )}

            {message && (
                <div className={`rounded-xl p-3 text-sm flex items-start gap-2 ${
                    message.type === 'ok'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-100'
                        : 'bg-rose-50 text-rose-700 border border-rose-100'
                }`}>
                    <span className="flex-1 break-words">{message.text}</span>
                    <button onClick={() => setMessage(null)}><X size={16} /></button>
                </div>
            )}

            <section className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <label className="block sm:col-span-2">
                        <span className="text-xs font-bold text-gray-600">SMTP 서버 주소 *</span>
                        <input
                            value={form.host}
                            onChange={e => set('host', e.target.value)}
                            placeholder="smtp.bit.kr"
                            className={inputCls}
                        />
                    </label>
                    <label className="block">
                        <span className="text-xs font-bold text-gray-600">포트</span>
                        <input
                            type="number"
                            value={form.port}
                            onChange={e => set('port', Number(e.target.value))}
                            className={inputCls}
                        />
                    </label>
                </div>

                <label className="flex items-center gap-2 text-sm text-gray-700">
                    <input
                        type="checkbox"
                        checked={form.use_tls}
                        onChange={e => set('use_tls', e.target.checked)}
                        className="w-4 h-4 rounded border-gray-300"
                    />
                    STARTTLS 사용 (포트 465는 자동으로 SSL 접속하며 이 설정과 무관합니다)
                </label>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <label className="block">
                        <span className="text-xs font-bold text-gray-600">계정 (username)</span>
                        <input
                            value={form.username}
                            onChange={e => set('username', e.target.value)}
                            placeholder="noreply@bit.kr"
                            className={inputCls}
                        />
                    </label>
                    <label className="block">
                        <span className="text-xs font-bold text-gray-600">
                            비밀번호 {form.password_set && <span className="text-emerald-600">(저장됨)</span>}
                        </span>
                        {/*
                          입력란은 항상 비운 채로 시작한다. 마스킹 값을 넣어두면
                          포커스만 하고 지웠다가 저장할 때 비밀번호가 삭제되는 사고가 난다.
                          비워두면 '변경 안 함'이고, 입력하면 그 값으로 교체된다.
                        */}
                        <input
                            type="password"
                            value={newPassword}
                            onChange={e => setNewPassword(e.target.value)}
                            placeholder={form.password_set ? '변경할 때만 입력' : '비밀번호'}
                            className={inputCls}
                        />
                    </label>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <label className="block">
                        <span className="text-xs font-bold text-gray-600">발신자 이름</span>
                        <input
                            value={form.from_name}
                            onChange={e => set('from_name', e.target.value)}
                            placeholder="BIT Wellness Center"
                            className={inputCls}
                        />
                    </label>
                    <label className="block">
                        <span className="text-xs font-bold text-gray-600">발신 주소 *</span>
                        <input
                            value={form.from_email}
                            onChange={e => set('from_email', e.target.value)}
                            placeholder="noreply@bit.kr"
                            className={inputCls}
                        />
                    </label>
                </div>

                <button
                    onClick={save}
                    disabled={saving || !form.host.trim() || !form.from_email.trim()}
                    className="w-full bg-blue-600 text-white font-bold py-3 rounded-xl hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                    {saving ? <Loader2 size={18} className="animate-spin" /> : <><Save size={16} /> 설정 저장</>}
                </button>
            </section>

            <section className="rounded-2xl bg-white p-5 shadow-sm border border-gray-100 space-y-3">
                <h3 className="font-bold text-gray-800 text-sm">테스트 발송</h3>
                <p className="text-xs text-gray-500">
                    저장된 설정으로 실제 메일을 보내 봅니다. 실패하면 원인이 그대로 표시됩니다.
                </p>
                <div className="flex gap-2">
                    <input
                        value={testEmail}
                        onChange={e => setTestEmail(e.target.value)}
                        placeholder="받는 사람 주소"
                        className="flex-1 rounded-xl border border-gray-200 bg-gray-50 p-2.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                        onClick={sendTest}
                        disabled={testing || !testEmail.trim() || !form.configured}
                        className="px-4 bg-gray-800 text-white font-bold rounded-xl hover:bg-gray-900 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-1.5 shrink-0"
                    >
                        {testing ? <Loader2 size={16} className="animate-spin" /> : <><Send size={14} /> 발송</>}
                    </button>
                </div>
                {!form.configured && (
                    <p className="text-xs text-gray-400">서버 주소와 발신 주소를 저장한 뒤 사용할 수 있습니다.</p>
                )}
            </section>
        </div>
    );
}
