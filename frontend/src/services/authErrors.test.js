import assert from 'node:assert/strict';
import { test } from 'node:test';
import axios from 'axios';
import {
    AuthApiError,
    AuthRetryableFetchError,
    AuthSessionMissingError,
} from '@supabase/supabase-js';
import { classifyAuthError } from './authErrors.js';

test('nhận diện các mã lỗi phiên không còn hợp lệ', () => {
    for (const code of [
        'session_not_found',
        'session_expired',
        'refresh_token_not_found',
        'refresh_token_already_used',
    ]) {
        const error = new AuthApiError('Test Auth error', 400, code);
        assert.equal(classifyAuthError(error), 'expired');
    }
});

test('thiếu phiên Auth được nhận diện là expired', () => {
    assert.equal(
        classifyAuthError(new AuthSessionMissingError()),
        'expired',
    );
});

test('lỗi kết nối hoặc dịch vụ có thể thử lại là temporary', () => {
    for (const status of [0, 503]) {
        const error = new AuthRetryableFetchError('Test retry', status);
        assert.equal(classifyAuthError(error), 'temporary');
    }
});

test('HTTP 401 hoặc 403 từ backend không tự bị coi là hết phiên', () => {
    for (const status of [401, 403]) {
        const error = new axios.AxiosError(
            'Test backend error',
            'ERR_BAD_RESPONSE',
            {},
            null,
            { status },
        );
        assert.equal(classifyAuthError(error), 'unknown');
    }
});

test('lỗi chưa xác định không tự bị coi là hết phiên', () => {
    for (const error of [
        null,
        undefined,
        new Error('Test unknown error'),
        new AuthApiError('Test invalid JWT', 401, 'bad_jwt'),
        new AuthApiError('Test permission', 403, 'not_admin'),
    ]) {
        assert.equal(classifyAuthError(error), 'unknown');
    }
});

test('object chỉ có code không được coi là lỗi Supabase Auth', () => {
    assert.equal(
        classifyAuthError({ code: 'session_expired' }),
        'unknown',
    );
});