
// WonderBEER minimal autocomplete
(function(){
  function $(sel, root=document){ return root.querySelector(sel); }
  function $all(sel, root=document){ return Array.from(root.querySelectorAll(sel)); }

  function createList(input){
    const wrap = document.createElement('div');
    wrap.className = 'wb-ac-list';
    wrap.style.position = 'absolute';
    wrap.style.zIndex = 9999;
    wrap.style.display = 'none';
    document.body.appendChild(wrap);
    const position = ()=>{
      const r = input.getBoundingClientRect();
      wrap.style.left = (window.scrollX + r.left) + 'px';
      wrap.style.top  = (window.scrollY + r.bottom + 2) + 'px';
      wrap.style.width = r.width + 'px';
    };
    position();
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, true);
    return wrap;
  }

  function render(wrap, items){
    wrap.innerHTML = '';
    if(!items || !items.length){ wrap.style.display='none'; return; }
    const ul = document.createElement('ul');
    ul.className='wb-ac-ul';
    items.slice(0,12).forEach((t,i)=>{
      const li = document.createElement('li');
      li.className='wb-ac-item';
      li.textContent = t;
      li.setAttribute('data-value', t);
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
    wrap.style.display='block';
  }

  // Keyboard navigation
  function enableKeyboard(input, wrap){
    let idx = -1;
    input.addEventListener('keydown', (e)=>{
      const items = $all('.wb-ac-item', wrap);
      if(!items.length) return;
      if(e.key === 'ArrowDown'){ idx = Math.min(idx+1, items.length-1); highlight(items, idx); e.preventDefault(); }
      else if(e.key === 'ArrowUp'){ idx = Math.max(idx-1, 0); highlight(items, idx); e.preventDefault(); }
      else if(e.key === 'Enter'){ if(idx>=0){ choose(input, items[idx]); } }
      else if(e.key === 'Escape'){ wrap.style.display='none'; }
    });
  }
  function highlight(items, idx){
    items.forEach(el=>el.classList.remove('wb-ac-active'));
    if(idx>=0 && items[idx]) items[idx].classList.add('wb-ac-active');
  }
  function choose(input, item){
    const v = item.getAttribute('data-value');
    input.value = v;
    input.dispatchEvent(new Event('change'));
    document.querySelectorAll('.wb-ac-list').forEach(w=>w.style.display='none');
  }

  function attach(input){
    const type = input.getAttribute('data-suggest');
    if(!type) return;
    const wrap = createList(input);
    enableKeyboard(input, wrap);

    input.addEventListener('input', async (e)=>{
      const q = input.value.trim();
      if(q.length < 2){ wrap.style.display='none'; return; }
      try{
        const res = await fetch(`/api/suggest?type=${encodeURIComponent(type)}&q=${encodeURIComponent(q)}`);
        if(!res.ok) throw new Error('net');
        const data = await res.json();
        render(wrap, data.suggestions || []);
      }catch(err){
        wrap.style.display='none';
      }
    });

    document.addEventListener('click', (e)=>{
      if(wrap.contains(e.target)) return;
      if(e.target.classList && e.target.classList.contains('wb-ac-item')){
        choose(input, e.target);
      }else if(e.target !== input){
        wrap.style.display='none';
      }
    });
  }

  window.addEventListener('DOMContentLoaded', ()=>{
    document.querySelectorAll('input[data-suggest]').forEach(attach);
  });
})();
