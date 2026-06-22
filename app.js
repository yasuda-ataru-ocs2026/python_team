let categories =
JSON.parse
/*
文字列
↓
JavaScriptで使える形
 */
(
    localStorage.getItem("categories")
    /*
    簡易的なDBみたいなもの
    */
) || [
    {
        name:"住宅",
        amount:60000
    },
    {
        name:"現金・カード",
        amount:70000
    },
    {
        name:"食費",
        amount:40000
    }
];
 
/*
ブラウザに保存済みの支出データを取得
↓
あれば使う
↓
なければ初期データを使う
*/
 
let budget =
Number(
    localStorage.getItem("budget")
) || 0;
/*
保存されているデータを取得
*/
 
let editIndex = null;
 
const colors = [
    "#41d6a4",
    "#ffb366",
    "#ff6b81",
    "#7f5af0",
    "#00b4d8",
    "#ffd166",
    "#06d6a0"
];
 
function saveData(){
 
    localStorage.setItem(
        "categories",
        JSON.stringify(categories)
    );
 
    localStorage.setItem(
        "budget",
        budget
    );
}
 
const ctx =
document.getElementById(
    "expenseChart"
);
 
const chart = new Chart(ctx,{
    type:"doughnut",
    data:{
        labels:[],
        datasets:[{
            data:[],
            backgroundColor:[]
        }]
    }
});
 
function render(){
 
    const list =
    document.getElementById(
        "categoryList"
    );
 
    list.innerHTML = "";
 
    categories.forEach(
        (item,index)=>{
 
        list.innerHTML += `
        <div class="category">
 
            <div>
                <strong>${item.name}</strong>
                <br>
                ¥${item.amount.toLocaleString()}
            </div>
 
            <div class="actions">
 
                <button
                onclick="editItem(${index})">
                ✏️
                </button>
 
                <button
                onclick="deleteItem(${index})">
                🗑️
                </button>
 
            </div>
 
        </div>
 
        <div class="progress">
            <div
            class="bar"
            style="width:${Math.min(item.amount/1000,100)}%">
            </div>
        </div>
        `;
    });
 
    chart.data.labels =
    categories.map(c=>c.name);
 
    chart.data.datasets[0].data =
    categories.map(c=>c.amount);
 
    chart.data.datasets[0].backgroundColor =
    colors.slice(0,categories.length);
 
    chart.update();
 
    const total =
    categories.reduce(
        (sum,item)=>
        sum + item.amount,
        0
    );
 
    const remaining =
    budget - total;
 
    document.getElementById(
        "remainingBudget"
    ).innerText =
    `¥${remaining.toLocaleString()}`;
 
    document.getElementById(
        "budgetInput"
    ).value = budget;
}
 
render();
 
const modal =
document.getElementById(
    "modal"
);
 
document
.querySelector(".add-btn")
.addEventListener(
"click",
()=>{
 
    editIndex = null;
 
    document.getElementById(
        "modalTitle"
    ).innerText =
    "支出追加";
 
    document.getElementById(
        "categoryName"
    ).value = "";
 
    document.getElementById(
        "amount"
    ).value = "";
 
    modal.classList.remove(
        "hidden"
    );
});
 
modal.addEventListener(
"click",
e=>{
 
    if(e.target === modal){
 
        modal.classList.add(
            "hidden"
        );
    }
});
 
document
.getElementById(
    "saveExpense"
)
.addEventListener(
"click",
()=>{
 
    const name =
    document.getElementById(
        "categoryName"
    ).value;
 
    const amount =
    Number(
        document.getElementById(
            "amount"
        ).value
    );
 
    if(!name || !amount){
        return;
    }
 
    if(editIndex === null){
 
        categories.push({
            name,
            amount
        });
 
    }else{
 
        categories[editIndex] = {
            name,
            amount
        };
    }
 
    saveData();
    render();
 
    modal.classList.add(
        "hidden"
    );
});
 
window.editItem =
function(index){
 
    editIndex = index;
 
    const item =
    categories[index];
 
    document.getElementById(
        "modalTitle"
    ).innerText =
    "支出編集";
 
    document.getElementById(
        "categoryName"
    ).value =
    item.name;
 
    document.getElementById(
        "amount"
    ).value =
    item.amount;
 
    modal.classList.remove(
        "hidden"
    );
};
 
window.deleteItem =
function(index){
 
    if(
        confirm(
        "削除しますか？"
        )
    ){
 
        categories.splice(
            index,
            1
        );
 
        saveData();
        render();
    }
};
 
document
.getElementById(
    "saveBudget"
)
.addEventListener(
"click",
()=>{
 
    budget =
    Number(
        document.getElementById(
            "budgetInput"
        ).value
    );
 
    saveData();
    render();
});