'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { API_URL } from '@/lib/api';
import {
  UserPlus,
  Trash2,
  Upload,
  ArrowLeft,
  Search,
  CheckCircle,
  AlertCircle
} from 'lucide-react';

interface User {
  id: number;
  name: string;
  birth_date: string;
  department: string | null;
  role: string;
}

export default function AdminUsersPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'list' | 'create' | 'upload'>('list');
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

  // Search/Filter state
  const [searchTerm, setSearchTerm] = useState('');

  // Create User Form State
  const [newUser, setNewUser] = useState({ name: '', birth_date: '', department: '' });

  // Upload State
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    if (activeTab === 'list') {
      fetchUsers();
    }
  }, [activeTab]);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_URL}/api/users/`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to fetch users');
      setUsers(await res.json());
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteUser = async (id: number) => {
    if (!confirm('정말 이 사용자를 삭제하시겠습니까?')) return;

    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_URL}/api/users/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to delete user');

      setMessage({ type: 'success', text: '사용자가 삭제되었습니다.' });
      fetchUsers(); // Refresh list
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_URL}/api/users/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newUser)
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create user');

      setMessage({ type: 'success', text: '사용자가 성공적으로 등록되었습니다.' });
      setNewUser({ name: '', birth_date: '', department: '' });
      setActiveTab('list'); // Go to list view
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setLoading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_URL}/api/users/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload failed');

      setMessage({
        type: 'success',
        text: data.message + (data.errors?.length ? ` (Errors: ${data.errors.length})` : '')
      });
      setActiveTab('list');
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const filteredUsers = users.filter(user =>
    user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (user.department && user.department.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="min-h-screen bg-gray-50 font-sans text-gray-900">
      {/* Header */}
      <div className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/admin')}
              className="p-2 rounded-full hover:bg-gray-100 transition-colors text-gray-500"
            >
              <ArrowLeft size={20} />
            </button>
            <h1 className="text-xl font-bold text-gray-800">사용자 관리</h1>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Navigation Tabs */}
        <div className="flex space-x-1 rounded-xl bg-gray-200 p-1 mb-8 w-fit mx-auto">
          {(['list', 'create', 'upload'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`
                w-32 py-2.5 text-sm font-medium leading-5 rounded-lg transition-all duration-200
                ${activeTab === tab
                  ? 'bg-white text-blue-700 shadow'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-200/50'
                }
              `}
            >
              {tab === 'list' && '사용자 목록'}
              {tab === 'create' && '개별 등록'}
              {tab === 'upload' && '일괄 등록'}
            </button>
          ))}
        </div>

        {/* Feedback Message */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg flex items-center gap-3 shadow-sm ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
            }`}>
            {message.type === 'success' ? <CheckCircle size={20} /> : <AlertCircle size={20} />}
            <p className="text-sm font-medium">{message.text}</p>
            <button onClick={() => setMessage(null)} className="ml-auto text-sm hover:underline">닫기</button>
          </div>
        )}

        {/* Content Area */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden min-h-[500px]">

          {/* List View */}
          {activeTab === 'list' && (
            <div className="p-6">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-lg font-bold text-gray-800">등록된 사용자 ({users.length})</h2>
                <div className="relative w-64">
                  <input
                    type="text"
                    placeholder="이름 또는 부서 검색..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                  />
                  <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
                </div>
              </div>

              {loading ? (
                <div className="flex justify-center items-center h-64 text-gray-400">Loading...</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">이름</th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">비밀번호</th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">부서</th>
                        <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">역할</th>
                        <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">관리</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {filteredUsers.length > 0 ? (
                        filteredUsers.map((user) => (
                          <tr key={user.id} className="hover:bg-gray-50 transition-colors">
                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{user.name}</td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">******</td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                              {user.department ? (
                                <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                                  {user.department}
                                </span>
                              ) : '-'}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                              <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${user.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-800'
                                }`}>
                                {user.role}
                              </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                              <button
                                onClick={() => handleDeleteUser(user.id)}
                                className="text-red-400 hover:text-red-600 transition-colors p-1"
                              >
                                <Trash2 size={18} />
                              </button>
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={5} className="px-6 py-12 text-center text-sm text-gray-500">
                            검색 결과가 없습니다.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Create User View */}
          {activeTab === 'create' && (
            <div className="max-w-md mx-auto py-12 px-6">
              <div className="text-center mb-8">
                <div className="bg-blue-100 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 text-blue-600">
                  <UserPlus size={32} />
                </div>
                <h2 className="text-2xl font-bold text-gray-900">사용자 개별 등록</h2>
                <p className="text-sm text-gray-500 mt-2">새로운 사용자의 정보를 입력해주세요.</p>
              </div>

              <form onSubmit={handleCreateUser} className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">이름</label>
                  <input
                    type="text"
                    required
                    value={newUser.name}
                    onChange={e => setNewUser({ ...newUser, name: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                    placeholder="홍길동"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">생년월일 (6자리)</label>
                  <input
                    type="text"
                    required
                    maxLength={6}
                    value={newUser.birth_date}
                    onChange={e => setNewUser({ ...newUser, birth_date: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                    placeholder="900101"
                  />
                  <p className="mt-1 text-xs text-gray-400">주민등록번호 앞 6자리를 입력하세요.</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">부서 (선택)</label>
                  <input
                    type="text"
                    value={newUser.department}
                    onChange={e => setNewUser({ ...newUser, department: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                    placeholder="영업팀"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors disabled:opacity-50"
                >
                  {loading ? '등록 중...' : '사용자 등록'}
                </button>
              </form>
            </div>
          )}

          {/* Bulk Upload View */}
          {activeTab === 'upload' && (
            <div className="max-w-md mx-auto py-12 px-6">
              <div className="text-center mb-8">
                <div className="bg-green-100 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 text-green-600">
                  <Upload size={32} />
                </div>
                <h2 className="text-2xl font-bold text-gray-900">사용자 일괄 등록</h2>
                <p className="text-sm text-gray-500 mt-2">엑셀 파일을 업로드하여 사용자를 한 번에 등록합니다.</p>
              </div>

              <form onSubmit={handleUpload} className="space-y-6">
                <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:bg-gray-50 transition-colors cursor-pointer relative">
                  <input
                    type="file"
                    accept=".xlsx, .xls"
                    onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  />
                  <div className="space-y-2">
                    <Upload className="mx-auto h-12 w-12 text-gray-400" />
                    <div className="text-sm text-gray-600">
                      {file ? (
                        <span className="font-semibold text-blue-600">{file.name}</span>
                      ) : (
                        <span>파일을 드래그하거나 클릭하여 선택하세요</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500">.xlsx, .xls 파일 허용</p>
                  </div>
                </div>

                <div className="bg-blue-50 rounded-lg p-4">
                  <h4 className="text-sm font-medium text-blue-800 mb-2">필수 엑셀 컬럼</h4>
                  <ul className="text-xs text-blue-600 space-y-1 list-disc list-inside">
                    <li>Name (이름)</li>
                    <li>BirthDate (생년월일 6자리)</li>
                    <li>Department (부서 - 선택)</li>
                  </ul>
                </div>

                <button
                  type="submit"
                  disabled={!file || loading}
                  className="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition-colors disabled:opacity-50"
                >
                  {loading ? '업로드 중...' : '엑셀 업로드'}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
