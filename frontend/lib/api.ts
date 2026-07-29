export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002';

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_name: string;
  role: string;
}

export const fetcher = async (url: string, options: RequestInit = {}) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  const headers = {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
    ...(options.headers || {}),
  } as HeadersInit;

  const response = await fetch(`${API_URL}${url}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'An error occurred' }));
    throw new Error(error.detail || response.statusText);
  }

  return response.json();
}

export interface GymStatus {
  count: number;
  congestion: 'free' | 'normal' | 'busy' | 'low' | 'medium' | 'high';
  my_status: 'in' | 'out';
  capacity: number;
}

export const getGymStatus = async (): Promise<GymStatus> => {
  return fetcher('/api/gym/status');
};

export const accessGym = async () => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_URL}/api/gym/access`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  return res.json();
};

export interface GolfSettings {
  weekday_slots: { start: string; end: string }[];
  weekend_start: number;
  weekend_end: number;
}

export interface GolfSlot {
  time: string;
  end_time: string;
  available: boolean;
  type: 'weekday' | 'weekend';
  taken_by_priority: number | null;  // 1,2,3 또는 null
  taken_res_id: number | null;
  can_preempt: boolean;              // 3시간 전 조건 충족 여부
}

export interface Reservation {
  id: number;
  start_time: string;
  end_time: string;
  participant_count: number;
  companions: string | null;
  status: string;
  priority: number;  // 1: 최우선, 2: 우선, 3: 양보
}

export const getGolfSlots = async (date: string): Promise<GolfSlot[]> => {
  return fetcher(`/api/golf/slots?date=${date}`);
};

export const reserveGolf = async (data: { start_time: string, end_time: string, participant_count: number, companions: string | null, priority: number }) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_URL}/api/golf/reserve`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Reservation failed');
  }
  return res.json();
};

export const cancelGolfReservation = async (id: number) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_URL}/api/golf/cancel/${id}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Cancellation failed');
  }
  return res.json();
};

export async function accessGolf() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const res = await fetch(`${API_URL}/api/golf/access`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  if (!res.ok) {
    throw new Error('Failed to access golf facility');
  }
  return res.json();
};

export const getMyReservations = async (): Promise<Reservation[]> => {
  return fetcher('/api/golf/my');
};

export interface UserDashboardStats {
  monthly_count: number;
  has_today_reservation: boolean;
}

export const getUserDashboard = async (): Promise<UserDashboardStats> => {
  return fetcher('/api/users/me/dashboard');
};

// --- 비트별장(휴양소) ---

export interface Villa {
  id: number;
  name: string;
  capacity: number;
  address: string;
  size: string;
  notice: string;
  default_checkin_time: string;
  default_checkout_time: string;
}

export interface VillaRound {
  target_year: number;
  target_month: number;
  apply_start: string;
  apply_end: string;
  notify_date: string;
  status: string;
  is_open: boolean;
  days_left: number;
  peak_months: number[];
  peak_max_nights: number | null;
}

export type VillaStatus =
  | 'applied'
  | 'confirmed'
  | 'cancel_requested'
  | 'canceled'
  | 'rejected';

export interface VillaCalendarItem {
  id: number;
  start_date: string;   // YYYY-MM-DD (체크인)
  end_date: string;     // YYYY-MM-DD (체크아웃, 배타적)
  nights: number;
  status: VillaStatus;
  is_mine: boolean;
  participant_count: number;
  user_name: string | null;   // 경합 중인 타인 신청은 null
  user_dept: string | null;
}

/** regular: 정규예약 접수중 / open: 결과 통보 후 선착순 / closed: 신청 불가(조회만) */
export type VillaBookingMode = 'regular' | 'open' | 'closed';

export interface VillaCalendar {
  year: number;
  month: number;
  facility_id: number;
  facility_name: string;
  capacity: number;
  booking_mode: VillaBookingMode;
  items: VillaCalendarItem[];
}

export interface VillaMyReservation {
  id: number;
  facility_id: number;
  facility_name: string | null;
  start_date: string;
  end_date: string;
  nights: number;
  checkin_time: string | null;
  checkout_time: string | null;
  // true면 앞뒤로 붙는 예약이 있어 정규 시간으로 강제 적용된 상태다.
  checkin_time_forced: boolean;
  checkout_time_forced: boolean;
  participant_count: number;
  status: VillaStatus;
  booking_type: string;
  cancel_reason: string | null;
  needs_extra_info: boolean;
}

export const getVillas = async (): Promise<Villa[]> => {
  return fetcher('/api/villa/facilities');
};

export const getVillaRound = async (): Promise<VillaRound> => {
  return fetcher('/api/villa/current-round');
};

export const getVillaCalendar = async (
  facilityId: number,
  year: number,
  month: number
): Promise<VillaCalendar> => {
  return fetcher(`/api/villa/calendar?facility_id=${facilityId}&year=${year}&month=${month}`);
};

export const getMyVillaReservations = async (): Promise<VillaMyReservation[]> => {
  return fetcher('/api/villa/my');
};

export interface VillaApplyResult {
  id: number;
  status: VillaStatus;
  booking_type: string;
  checkin_time: string | null;
  checkout_time: string | null;
  checkin_time_forced: boolean;
  checkout_time_forced: boolean;
}

export const applyVilla = async (data: {
  facility_id: number;
  start_date: string;
  end_date: string;
  checkin_time: string;
  checkout_time: string;
  participant_count: number;
}): Promise<VillaApplyResult> => {
  return fetcher('/api/villa/apply', {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

export const cancelVillaApplication = async (id: number) => {
  return fetcher(`/api/villa/cancel/${id}`, { method: 'POST' });
};

export const requestVillaCancel = async (id: number, reason: string | null) => {
  return fetcher(`/api/villa/cancel-request/${id}`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
};

export interface VillaExtraInfo {
  id: number;
  facility_name: string | null;
  start_date: string;
  end_date: string;
  nights: number;
  checkin_time: string | null;
  checkout_time: string | null;
  checkin_time_forced: boolean;
  checkout_time_forced: boolean;
  participant_count: number;
  status: VillaStatus;
  vehicle_count: number | null;
  vehicle_numbers: string | null;
  adult_count: number | null;
  child_count: number | null;
  contact_phone: string | null;
  submitted: boolean;
  composition_total: number;
  warning?: string | null;
}

export const getVillaExtraInfo = async (id: number): Promise<VillaExtraInfo> => {
  return fetcher(`/api/villa/${id}/extra`);
};

export const saveVillaExtraInfo = async (
  id: number,
  data: {
    vehicle_count: number;
    vehicle_numbers: string | null;
    adult_count: number;
    child_count: number;
    contact_phone: string;  // 필수 입력
  }
): Promise<VillaExtraInfo> => {
  return fetcher(`/api/villa/${id}/extra`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
};

// --- 이용안내 (체크인 전날) ---

export type VillaAccessStep = { icon: 'key' | 'bellhop' | 'bell' } | { code: string };

export interface VillaAccessLine {
  label: string;
  steps?: VillaAccessStep[];
  plain?: string;
}

export interface VillaGuide {
  reservation: {
    id: number;
    facility_name: string | null;
    start_date: string;
    end_date: string;
    checkin_time: string | null;
    checkout_time: string | null;
    participant_count: number;
  };
  address: string;
  address_note: string;
  access: VillaAccessLine[];
  notes: string[];
  wifi: { network: string; password: string };
  key_return_notice: string;
  emergency_contact: string;
}

export const getVillaGuide = async (id: number): Promise<VillaGuide> => {
  return fetcher(`/api/villa/${id}/guide`);
};

// --- 퇴실 체크사항 (체크아웃 당일) ---

export interface VillaChecklistItem {
  label: string;
  sub: string | null;
}

export interface VillaCheckout {
  reservation: { id: number; facility_name: string | null; start_date: string; end_date: string };
  checklist: VillaChecklistItem[];
  key_return_notice: string;
  emergency_contact: string;
  submitted: boolean;
  checked: boolean[] | null;
  notes: string | null;
}

export const getVillaCheckout = async (id: number): Promise<VillaCheckout> => {
  return fetcher(`/api/villa/${id}/checkout`);
};

export const submitVillaCheckout = async (
  id: number,
  data: { checked: boolean[]; notes: string | null }
): Promise<{ message: string }> => {
  return fetcher(`/api/villa/${id}/checkout`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
};
