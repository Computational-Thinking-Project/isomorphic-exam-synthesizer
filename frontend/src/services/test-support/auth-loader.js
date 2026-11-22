// Chỉ stub import Supabase của các module được kiểm thử.
const consumers = new Map([
    [new URL('../api.js', import.meta.url).href, './supabase.js'],
    [new URL('../authRefresh.js', import.meta.url).href, './supabase.js'],
    [new URL('../../App.jsx', import.meta.url).href, './services/supabase.js'],
]);

export function resolve(specifier, context, nextResolve) {
    if (consumers.get(context.parentURL) === specifier) {
        return {
            url: new URL('./supabase.stub.js', import.meta.url).href,
            shortCircuit: true,
        };
    }

    return nextResolve(specifier, context);
}
