//! JNI cho com.vtgt.reviewphim.SeaG2p - gọi C ABI của sea-g2p (chuẩn hóa chữ + đổi sang âm vị).
use jni::objects::{JClass, JString};
use jni::sys::{jboolean, jlong, jstring};
use jni::JNIEnv;
use sea_g2p_rs::capi::{
    sea_g2p_close, sea_g2p_last_error, sea_g2p_open, sea_g2p_phonemize, sea_g2p_string_free, SeaG2p,
};
use std::ffi::{CStr, CString};

fn last_error() -> String {
    let p = sea_g2p_last_error();
    if p.is_null() {
        "lỗi không rõ".to_string()
    } else {
        unsafe { CStr::from_ptr(p) }.to_string_lossy().into_owned()
    }
}

fn throw(env: &mut JNIEnv, msg: &str) {
    let _ = env.throw_new("java/lang/IllegalStateException", msg);
}

#[no_mangle]
pub extern "system" fn Java_com_vtgt_reviewphim_SeaG2p_nativeOpen(mut env: JNIEnv, _c: JClass, path: JString) -> jlong {
    let p: String = match env.get_string(&path) {
        Ok(s) => s.into(),
        Err(_) => return 0,
    };
    let c = match CString::new(p) {
        Ok(c) => c,
        Err(_) => return 0,
    };
    let h = unsafe { sea_g2p_open(c.as_ptr()) };
    if h.is_null() {
        let e = last_error();
        throw(&mut env, &format!("sea-g2p: {e}"));
        return 0;
    }
    h as jlong
}

#[no_mangle]
pub extern "system" fn Java_com_vtgt_reviewphim_SeaG2p_nativePhonemize(
    mut env: JNIEnv,
    _c: JClass,
    handle: jlong,
    text: JString,
    punc_norm: jboolean,
) -> jstring {
    if handle == 0 {
        throw(&mut env, "sea-g2p chưa mở");
        return std::ptr::null_mut();
    }
    let t: String = match env.get_string(&text) {
        Ok(s) => s.into(),
        Err(_) => return std::ptr::null_mut(),
    };
    let c = match CString::new(t) {
        Ok(c) => c,
        Err(_) => {
            throw(&mut env, "chữ có ký tự NUL");
            return std::ptr::null_mut();
        }
    };
    let out = unsafe { sea_g2p_phonemize(handle as *const SeaG2p, c.as_ptr(), if punc_norm != 0 { 1 } else { 0 }) };
    if out.is_null() {
        let e = last_error();
        throw(&mut env, &format!("sea-g2p: {e}"));
        return std::ptr::null_mut();
    }
    let s = unsafe { CStr::from_ptr(out) }.to_string_lossy().into_owned();
    unsafe { sea_g2p_string_free(out) };
    match env.new_string(s) {
        Ok(j) => j.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_vtgt_reviewphim_SeaG2p_nativeClose(_env: JNIEnv, _c: JClass, handle: jlong) {
    if handle != 0 {
        unsafe { sea_g2p_close(handle as *mut SeaG2p) };
    }
}
