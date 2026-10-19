// Chỉ thay dependency Supabase của hai module cần kiểm; giữ nguyên source.
const consumers = new Set([
    new URL('../api.js', import.meta.url).href,
    new URL('../authRefresh.js', import.meta.url).href,
]);

export function resolve(specifier, context, nextResolve) {
    if (specifier === './supabase.js' && consumers.has(context.parentURL)) {
        return {
            url: new URL('./supabase.stub.js', import.meta.url).href,
            shortCircuit: true,
        };
    }

    return nextResolve(specifier, context);
}
