/* Yoink Caddie — client-side style engine.
   Crown demo pages embed course packs (#cpacks) and this script; it injects a
   style picker and re-dresses every hole from the same measurements. The Book
   is the locked brand default; Gen 11 restores the server-rendered Crown art.
   Choice persists per browser via localStorage. */
(function(){



function rng(seed){ var s=0; for(var i=0;i<seed.length;i++) s=(s*31+seed.charCodeAt(i))>>>0;
  return function(){ s=(s+0x6D2B79F5)>>>0; var t=Math.imul(s^(s>>>15),1|s);
    t=(t+Math.imul(t^(t>>>7),61|t))^t; return ((t^(t>>>14))>>>0)/4294967296; }; }
function smooth(pts, closed){
  var p=pts.slice(); if(closed && (p[0][0]!==p[p.length-1][0]||p[0][1]!==p[p.length-1][1])) p.push(p[0]);
  if(closed) p.pop();
  var n=p.length, d='M'+p[0][0].toFixed(1)+','+p[0][1].toFixed(1);
  function at(i){ return p[((i%n)+n)%n]; }
  var end=closed?n:n-1;
  for(var i=0;i<end;i++){
    var p0=at(i-1),p1=at(i),p2=at(i+1),p3=at(i+2);
    if(!closed){ if(i===0)p0=p1; if(i===n-2)p3=p2; }
    var c1=[p1[0]+(p2[0]-p0[0])/6, p1[1]+(p2[1]-p0[1])/6];
    var c2=[p2[0]-(p3[0]-p1[0])/6, p2[1]-(p3[1]-p1[1])/6];
    d+='C'+c1[0].toFixed(1)+','+c1[1].toFixed(1)+' '+c2[0].toFixed(1)+','+c2[1].toFixed(1)+' '+p2[0].toFixed(1)+','+p2[1].toFixed(1);
  }
  return d+(closed?'Z':'');
}
var segs=[], totalLen=0;
function rebuildArc(){ segs=[]; totalLen=0; for(var i=0;i<G.line.length-1;i++){ var a=G.line[i],b=G.line[i+1];
  var L=Math.hypot(b[0]-a[0],b[1]-a[1]); segs.push({a:a,b:b,L:L}); totalLen+=L; } }
function lineAt(arc){ var t=Math.max(0,Math.min(arc,totalLen)), i=0;
  while(i<segs.length-1 && t>segs[i].L){ t-=segs[i].L; i++; }
  var s=segs[i], f=t/s.L;
  return { p:[s.a[0]+(s.b[0]-s.a[0])*f, s.a[1]+(s.b[1]-s.a[1])*f],
           d:[(s.b[0]-s.a[0])/s.L,(s.b[1]-s.a[1])/s.L] }; }
function corridor(a0,a1,wFn,R){
  var left=[], right=[], steps=26;
  for(var i=0;i<=steps;i++){
    var arc=a0+(a1-a0)*i/steps, q=lineAt(arc), w=wFn(arc)*(0.94+(R?R():0.5)*0.12);
    left.push([q.p[0]-q.d[1]*w, q.p[1]+q.d[0]*w]);
    right.push([q.p[0]+q.d[1]*w, q.p[1]-q.d[0]*w]);
  }
  return left.concat(right.reverse());
}
function fwWidth(arc){ var t=(arc-G.fwStart)/(totalLen-G.fwStart);
  return 15+14*Math.sin(Math.min(1,Math.max(0,t))*Math.PI)*1.05; }
function treeSpots(R){
  var out=[];
  G.stands.forEach(function(st){
    var n=Math.max(2,st.count+1);
    for(var i=0;i<n;i++){
      var arc=st.a0+(st.a1-st.a0)*(i+0.5)/n, q=lineAt(arc);
      var off=st.d+6+R()*10;
      out.push([q.p[0]+q.d[1]*off*st.side*-1, q.p[1]-q.d[0]*off*st.side*-1, 8+R()*7]);
    }
  });
  return out;
}
function inset(pts, f){
  var cx=0, cy=0; pts.forEach(function(p){cx+=p[0];cy+=p[1];});
  cx/=pts.length; cy/=pts.length;
  return pts.map(function(p){ return [cx+(p[0]-cx)*f, cy+(p[1]-cy)*f]; });
}




var G=null;   // page-space geometry, set per hole by renderBook

function renderBook(el, H, meta){
  var target=el.id || (el.id='ha'+H.hole);
  var INK='#14432A', MUT='#6D7770', FAINT='#9AA39C', ACID='#C7F24A', PENCIL='#55584F', TREE='#D6E0BE';
  var SUF='_'+target;
  var R=rng((meta.key||'course')+':'+H.hole+':book');

  // ---- fit raw yards geometry into the page art zone ----
  var pts=[];
  function eat(a){ (a||[]).forEach(function(p){ pts.push(p); }); }
  eat(H.line); eat(H.green); eat(H.tees);
  (H.bunkers||[]).forEach(eat); (H.waters||[]).forEach(eat);
  var xs=pts.map(function(p){return p[0];}), ys=pts.map(function(p){return p[1];});
  var minx=Math.min.apply(0,xs)-18, maxx=Math.max.apply(0,xs)+18;
  var miny=Math.min.apply(0,ys)-14, maxy=Math.max.apply(0,ys)+6;
  var s=Math.min(226/(maxx-minx), 484/(maxy-miny), H.par===3?2.1:1.35);
  var tx=-20-s*(minx+maxx)/2, ty=-16-s*maxy;
  function T(p){ return [p[0]*s+tx, p[1]*s+ty]; }
  function Tp(a){ return (a||[]).map(T); }

  G={ line:Tp(H.line), green:Tp(H.green), tees:Tp(H.tees),
      bunkers:(H.bunkers||[]).map(Tp), waters:(H.waters||[]).map(Tp),
      stands:(H.stands||[]).map(function(st){ return {d:st.d*s, a0:st.a0*s, a1:st.a1*s, side:st.side, count:st.count}; }),
      fwStart:(H.fw_start!=null?H.fw_start*s:null), bendAt:(H.bend?H.bend.at*s:null) };
  rebuildArc();

  var defs = "<defs>"
    +"<pattern id='bkgrid"+SUF+"' width='11' height='11' patternUnits='userSpaceOnUse'><path d='M11,0 L0,0 0,11' fill='none' stroke='#E4E1D2' stroke-width='0.5'/></pattern>"
    +"<filter id='bkpencil"+SUF+"'><feTurbulence type='fractalNoise' baseFrequency='0.09' numOctaves='2' seed='31'/><feDisplacementMap in='SourceGraphic' scale='1.6'/></filter>"
    +"<clipPath id='bkclip"+SUF+"'><rect x='24' y='-188' width='72' height='72'/></clipPath>"
    +"</defs>";
  var s2 = "<rect x='-155' y='-565' width='260' height='615' fill='#F6F4EB'/>";
  s2 += "<rect x='-136' y='-565' width='241' height='615' fill='url(#bkgrid"+SUF+")'/>";
  for(var i=0;i<13;i++){
    var y=-548+i*47;
    s2 += "<circle cx='-147' cy='"+y+"' r='3.4' fill='#F6F4EB' stroke='"+FAINT+"' stroke-width='1.2'/>";
    s2 += "<path d='M-147,"+(y-3.4)+" A6,6 0 0 1 -141,"+y+"' fill='none' stroke='"+MUT+"' stroke-width='1.4'/>";
  }
  s2 += "<line x1='-136' y1='-565' x2='-136' y2='50' stroke='#D9D5C4' stroke-width='0.8'/>";

  // ---- hole art ----
  if(G.fwStart!=null){
    s2 += "<path d='"+smooth(corridor(16*s,G.fwStart,function(a){return 12*s;},null),true)+"' fill='none' stroke='"+INK+"' stroke-width='0.7' stroke-dasharray='2 2.6' opacity='0.55'/>";
    var fwd = smooth(corridor(G.fwStart,totalLen-8*s,fwWidth,null),true);
    s2 += "<path d='"+fwd+"' fill='#EAEFE0' stroke='"+INK+"' stroke-width='1'/>";
  }
  G.waters.forEach(function(w){
    s2 += "<path d='"+smooth(w,true)+"' fill='#DEE9EA' stroke='"+INK+"' stroke-width='1.1'/>";
    s2 += "<path d='"+smooth(inset(w.slice(0,-1),0.72),true)+"' fill='none' stroke='#9CBEC2' stroke-width='0.6'/>";
    s2 += "<path d='"+smooth(inset(w.slice(0,-1),0.45),true)+"' fill='none' stroke='#9CBEC2' stroke-width='0.5' opacity='0.7'/>";
  });
  G.bunkers.forEach(function(b){
    s2 += "<path d='"+smooth(b,true)+"' fill='#F0EAD6' stroke='"+INK+"' stroke-width='0.9'/>";
  });
  s2 += "<path d='"+smooth(G.green,true)+"' fill='#DCE7CE' stroke='"+INK+"' stroke-width='1.4'/>";
  var pin=T([ (H.green.reduce(function(a,p){return a+p[0];},0)/H.green.length),
              (H.green.reduce(function(a,p){return a+p[1];},0)/H.green.length) ]);
  s2 += "<circle cx='"+pin[0].toFixed(1)+"' cy='"+pin[1].toFixed(1)+"' r='2.2' fill='"+ACID+"' stroke='"+INK+"' stroke-width='0.9'/>";
  G.tees.forEach(function(t){ s2 += "<rect x='"+(t[0]-3).toFixed(1)+"' y='"+(t[1]-1.8).toFixed(1)+"' width='6' height='3.6' fill='none' stroke='"+INK+"' stroke-width='0.9'/>"; });
  var trs=Math.min(1.15,Math.max(0.8,s));
  treeSpots(R).forEach(function(t){
    t[2]=t[2]*trs;
    var ell = "<ellipse cx='"+t[0].toFixed(1)+"' cy='"+t[1].toFixed(1)+"' rx='"+(t[2]*1.05).toFixed(1)+"' ry='"+(t[2]*0.5).toFixed(1)+"'/>"
      +"<ellipse cx='"+(t[0]-t[2]*0.55).toFixed(1)+"' cy='"+(t[1]+2.6).toFixed(1)+"' rx='"+(t[2]*0.55).toFixed(1)+"' ry='"+(t[2]*0.3).toFixed(1)+"'/>"
      +"<ellipse cx='"+(t[0]+t[2]*0.55).toFixed(1)+"' cy='"+(t[1]+3).toFixed(1)+"' rx='"+(t[2]*0.5).toFixed(1)+"' ry='"+(t[2]*0.28).toFixed(1)+"'/>";
    s2 += "<g stroke='"+INK+"' stroke-width='1.8' fill='"+TREE+"'>"+ell+"</g>";
    s2 += "<g fill='"+TREE+"' stroke='none'>"+ell+"</g>";
  });
  // the line: single dashed ink, arrowhead at the green
  s2 += "<path d='"+smooth(G.line,false)+"' fill='none' stroke='"+INK+"' stroke-width='1.7' stroke-dasharray='8 5' stroke-linecap='round'/>";
  var tip=lineAt(totalLen), bk=lineAt(totalLen-6);
  var dx=tip.p[0]-bk.p[0], dy=tip.p[1]-bk.p[1], dl=Math.hypot(dx,dy)||1; dx/=dl; dy/=dl;
  var ax=tip.p[0], ay=tip.p[1];
  s2 += "<path d='M"+(ax-4*dx-3*dy).toFixed(1)+","+(ay-4*dy+3*dx).toFixed(1)+" L"+ax.toFixed(1)+","+ay.toFixed(1)
      +" L"+(ax-4*dx+3*dy).toFixed(1)+","+(ay-4*dy-3*dx).toFixed(1)+"' fill='none' stroke='"+INK+"' stroke-width='1.3'/>";
  // pips each 100 yards
  for(var a=100; a<H.total-24; a+=100){
    var q=lineAt(a*s).p;
    s2 += "<circle cx='"+q[0].toFixed(1)+"' cy='"+q[1].toFixed(1)+"' r='2.2' fill='#F6F4EB' stroke='"+INK+"' stroke-width='0.9'/>";
    s2 += "<text x='"+(q[0]-6.5).toFixed(1)+"' y='"+(q[1]+2.2).toFixed(1)+"' font-size='6.2' font-family='Archivo, sans-serif' font-weight='700' fill='"+MUT+"' text-anchor='end'>"+a+"</text>";
  }
  function tick(arcY,label){
    var q=lineAt(arcY*s), w=(G.fwStart!=null?fwWidth(arcY*s):12*s)+7, pp=[q.d[1],-q.d[0]];
    var x1=q.p[0]-pp[0]*w, y1=q.p[1]-pp[1]*w, x2=q.p[0]+pp[0]*w, y2=q.p[1]+pp[1]*w;
    return "<path d='M"+x1.toFixed(1)+","+y1.toFixed(1)+" L"+x2.toFixed(1)+","+y2.toFixed(1)+"' stroke='"+INK+"' stroke-width='0.7' stroke-dasharray='2 2'/>"
      +"<text x='"+(x2+4).toFixed(1)+"' y='"+(y2+2.2).toFixed(1)+"' font-size='7' font-family='Archivo, sans-serif' font-weight='700' fill='"+INK+"'>"+label+"</text>";
  }
  if(H.fw_start!=null) s2 += tick(H.fw_start, H.fw_start+' FWY');
  if(H.bend && Math.abs(H.bend.at-(H.fw_start||-999))>18) s2 += tick(H.bend.at, H.bend.at+' TURN');
  // carry notes, right margin
  (H.carries||[]).forEach(function(c){
    if(c.kind==='fairway') return;
    if(c.kind==='sand' && c.at>H.total-30) return;
    var q=lineAt(c.at*s).p;
    var yy=Math.max(-500,Math.min(-30,q[1]));
    s2 += "<text x='96' y='"+yy.toFixed(1)+"' font-size='7' font-family='Archivo, sans-serif' font-weight='700' fill='"+INK+"' text-anchor='end'>CARRY "+c.at+" &#183; "+c.kind.toUpperCase()+"</text>";
  });
  // pencil live note (par 4/5): mid-approach position
  if(H.par>3){
    var frac=0.62, me=lineAt(totalLen*frac).p, rem=Math.round(H.total*(1-frac));
    s2 += "<circle cx='"+me[0].toFixed(1)+"' cy='"+me[1].toFixed(1)+"' r='2.6' fill='"+ACID+"' stroke='"+INK+"' stroke-width='1'/>";
    s2 += "<g filter='url(#bkpencil"+SUF+")'>";
    s2 += "<circle cx='-105' cy='"+(me[1]-2).toFixed(1)+"' r='13' fill='none' stroke='"+PENCIL+"' stroke-width='1.3'/>";
    s2 += "<path d='M-92,"+(me[1]-2).toFixed(1)+" L"+(me[0]-6).toFixed(1)+","+(me[1]-0.5).toFixed(1)+"' stroke='"+PENCIL+"' stroke-width='0.9' fill='none'/>";
    s2 += "</g>";
    s2 += "<text x='-105' y='"+(me[1]+3).toFixed(1)+"' font-size='13' font-family='Caveat, cursive' font-weight='600' fill='"+PENCIL+"' text-anchor='middle'>"+rem+"</text>";
    s2 += "<text x='-105' y='"+(me[1]-19).toFixed(1)+"' font-size='9' font-family='Caveat, cursive' fill='"+PENCIL+"' text-anchor='middle'>to ctr</text>";
  }
  // green detail box
  var gs=0, gc=pin;
  (function(){
    var gxs=H.green.map(function(p){return p[0];}), gys=H.green.map(function(p){return p[1];});
    var gw=Math.max.apply(0,gxs)-Math.min.apply(0,gxs), gh=Math.max.apply(0,gys)-Math.min.apply(0,gys);
    gs=52/Math.max(gw,gh);
    var rawc=[(Math.max.apply(0,gxs)+Math.min.apply(0,gxs))/2,(Math.max.apply(0,gys)+Math.min.apply(0,gys))/2];
    s2 += "<rect x='24' y='-188' width='72' height='72' fill='#FBFAF4' stroke='"+INK+"' stroke-width='1.1'/>";
    s2 += "<rect x='24' y='-188' width='72' height='72' fill='url(#bkgrid"+SUF+")'/>";
    s2 += "<g clip-path='url(#bkclip"+SUF+")'><g transform='translate(60,-152) scale("+gs.toFixed(3)+") translate("+(-rawc[0]).toFixed(1)+","+(-rawc[1]).toFixed(1)+")'>";
    s2 += "<path d='"+smooth(H.green,true)+"' fill='#DCE7CE' stroke='"+INK+"' stroke-width='"+(1.2/gs).toFixed(2)+"'/>";
    (H.bunkers||[]).forEach(function(b){
      var bc=[b.reduce(function(a,p){return a+p[0];},0)/b.length, b.reduce(function(a,p){return a+p[1];},0)/b.length];
      if(Math.hypot(bc[0]-rawc[0],bc[1]-rawc[1])<42)
        s2 += "<path d='"+smooth(b,true)+"' fill='#F0EAD6' stroke='"+INK+"' stroke-width='"+(0.8/gs).toFixed(2)+"'/>";
    });
    s2 += "<circle cx='"+rawc[0].toFixed(1)+"' cy='"+rawc[1].toFixed(1)+"' r='"+(1.8/gs).toFixed(2)+"' fill='"+ACID+"' stroke='"+INK+"' stroke-width='"+(0.7/gs).toFixed(2)+"'/>";
    s2 += "</g></g>";
  })();
  s2 += "<text x='60' y='-106' font-size='6.4' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='0.8' fill='"+INK+"' text-anchor='middle'>GREEN &#183; "+(H.depth||'?')+" DEEP</text>";

  // header
  var bkNm=(meta.name||'THE BOOK')
    .replace(/\s+(state park|country club|golf course|golf club|golf links|golf center|park golf course)$/i,'')
    .toUpperCase().slice(0,26);
  var bkFs=Math.max(6.5, Math.min(9.5, (125/Math.max(1,bkNm.length)-1.8)/0.62));
  var hn=(H.hole<10?'0':'')+H.hole;
  s2 += "<rect x='-128' y='-556' width='30' height='30' fill='none' stroke='"+INK+"' stroke-width='1.4'/>";
  s2 += "<text x='-113' y='-533' font-size='"+(H.hole<10?22:18)+"' font-family='Archivo, sans-serif' font-weight='900' fill='"+INK+"' text-anchor='middle'>"+H.hole+"</text>";
  s2 += "<g font-family='Archivo, sans-serif'>";
  s2 += "<text x='-90' y='-544' font-size='"+bkFs.toFixed(1)+"' font-weight='700' letter-spacing='1.8' fill='"+INK+"'>"+bkNm+"</text>";
  s2 += "<text x='-90' y='-532' font-size='6.6' font-weight='700' letter-spacing='1' fill='"+MUT+"'>YOINK &#183; THE BOOK</text>";
  s2 += "<text x='96' y='-544' font-size='6.4' font-weight='700' fill='"+FAINT+"' text-anchor='end'>PAGE "+hn+" / 18</text>";
  s2 += "</g>";
  s2 += "<line x1='-128' y1='-524' x2='-46' y2='-524' stroke='"+INK+"' stroke-width='1'/>";
  var vfs=Math.min(10.5, 216/(0.42*H.sign.length));
  s2 += "<text x='-128' y='0' font-size='"+vfs.toFixed(1)+"' font-family='Caveat, cursive' font-weight='600' fill='"+PENCIL+"'>"+H.sign+"</text>";

  // scorecard strip
  var cols=[['HOLE',''+H.hole,22],['PAR',''+H.par,22],['HCP','&#8212;',22],['BACK',''+H.yards.back,30],['MID',''+H.yards.mid,30],['FWD',''+H.yards.front,30],['SCORE','',46]];
  var x0=-128, y0=8, hh=32, tot=0; cols.forEach(function(c){tot+=c[2];});
  s2 += "<rect x='"+x0+"' y='"+y0+"' width='"+tot+"' height='"+hh+"' fill='#FBFAF4' stroke='"+INK+"' stroke-width='1.2'/>";
  var cx=x0;
  cols.forEach(function(c,i){
    if(i>0) s2 += "<line x1='"+cx+"' y1='"+y0+"' x2='"+cx+"' y2='"+(y0+hh)+"' stroke='"+INK+"' stroke-width='0.7'/>";
    s2 += "<text x='"+(cx+c[2]/2)+"' y='"+(y0+10)+"' font-size='5.6' font-family='Archivo, sans-serif' font-weight='700' letter-spacing='0.8' fill='"+MUT+"' text-anchor='middle'>"+c[0]+"</text>";
    if(c[1]) s2 += "<text x='"+(cx+c[2]/2)+"' y='"+(y0+25)+"' font-size='11.5' font-family='Archivo, sans-serif' font-weight='900' fill='"+INK+"' text-anchor='middle'>"+c[1]+"</text>";
    cx+=c[2];
  });
  s2 += "<line x1='"+x0+"' y1='"+(y0+14)+"' x2='"+(x0+tot)+"' y2='"+(y0+14)+"' stroke='"+INK+"' stroke-width='0.6'/>";
  s2 += "<g transform='translate(88,14) scale(0.16)'><path d='M50,5 c4.4,0 7.3,3.4 6.9,7.7 L52.7,103 h-5.4 L43.1,12.7 C42.7,8.4 45.6,5 50,5 Z' fill='"+INK+"'/><path d='M56.6,11 l31,9.6 -31,9.6 z' fill='"+ACID+"'/><circle cx='50' cy='125.5' r='9.6' fill='"+INK+"'/></g>";

  el.setAttribute('viewBox','-155 -565 260 615'); el.innerHTML=defs+s2;
}



// ---- style picker: injected into any Crown demo page ----
function boot(){
  var packsEl=document.getElementById('cpacks');
  if(!packsEl) return;
  var packs=JSON.parse(packsEl.textContent);
  var meta=window.CADDIE_COURSE||{};
  meta.n=packs.length;
  var byHole={}; packs.forEach(function(p){ byHole[p.hole]=p; });
  var arts=[].slice.call(document.querySelectorAll('svg.holeart')).map(function(el){
    var m=(el.getAttribute('aria-label')||'').match(/Hole (\d+)/);
    return m?{el:el, hole:+m[1], vb:el.getAttribute('viewBox'), html:el.innerHTML}:null;
  }).filter(Boolean);
  if(!arts.length) return;

  var css=".ykstyles{display:flex;gap:8px;align-items:center;margin:14px 0 2px;flex-wrap:wrap}"
    +".ykstyles span{font:700 10px Archivo,sans-serif;letter-spacing:.14em;color:var(--muted,#6D7770)}"
    +".ykchip{font:700 12px Archivo,sans-serif;border:1.5px solid var(--hair,#E3E3DC);background:var(--card,#fff);"
    +"color:var(--ink,#0C1710);border-radius:999px;padding:6px 14px;cursor:pointer}"
    +".ykchip.on{background:var(--forest,#14432A);border-color:var(--forest,#14432A);color:#F2F6EE}";
  var st=document.createElement('style'); st.textContent=css; document.head.appendChild(st);

  var bar=document.createElement('div'); bar.className='ykstyles';
  bar.innerHTML="<span>STYLE</span>";
  var defs=[['book','The Book'],['crown','Gen 11']];
  var btns={};
  defs.forEach(function(d){
    var b=document.createElement('button'); b.className='ykchip'; b.textContent=d[1];
    b.onclick=function(){ apply(d[0]); };
    btns[d[0]]=b; bar.appendChild(b);
  });
  var mast=document.querySelector('.mast');
  (mast||document.body).appendChild(bar);

  function apply(mode){
    defs.forEach(function(d){ btns[d[0]].classList.toggle('on', d[0]===mode); });
    arts.forEach(function(a){
      var H=byHole[a.hole];
      if(mode==='book' && H){ renderBook(a.el, H, meta); }
      else { a.el.setAttribute('viewBox', a.vb); a.el.innerHTML=a.html; }
    });
    try{ localStorage.setItem('caddie-style', mode); }catch(e){}
  }
  var want='book';
  try{ want=localStorage.getItem('caddie-style')||'book'; }catch(e){}
  apply(want==='crown'?'crown':'book');
}
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', boot); else boot();

})();
