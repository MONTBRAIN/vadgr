// Mirrors the backend api/models/auth.py PairResponse contract.
export interface PairResponse {
  host: string; // tailnet address, never 127.0.0.1
  port: number;
  pairing_token: string; // one-time, short-lived
  machine_name: string;
}
